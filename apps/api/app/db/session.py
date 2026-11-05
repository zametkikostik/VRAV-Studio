from collections.abc import AsyncGenerator
import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=settings.environment == "development",
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Request-scoped session.

    Endpoints may register storage keys in ``session.info['pending_storage_keys']``
    after a successful object put. On commit failure / rollback those keys are
    deleted (best-effort) so orphaned objects are not left behind.
    """
    async with AsyncSessionLocal() as session:
        session.info.setdefault("pending_storage_keys", [])
        try:
            yield session
            await session.commit()
            session.info["pending_storage_keys"] = []
        except Exception:
            await session.rollback()
            keys = list(session.info.get("pending_storage_keys") or [])
            session.info["pending_storage_keys"] = []
            if keys:
                try:
                    from app.services.storage import get_storage

                    storage = get_storage()
                    for key in keys:
                        try:
                            await storage.delete(key)
                        except Exception:
                            logger.warning(
                                "storage compensation delete failed",
                                extra={"key_prefix": str(key)[:32]},
                            )
                except Exception:
                    logger.warning("storage compensation unavailable")
            raise
