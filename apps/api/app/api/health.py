from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db

router = APIRouter()


@router.get("/health")
async def health():
    return {"status": "ok", "service": "vrav-api", "version": "0.2.2"}


@router.get("/health/db")
async def health_db(db: AsyncSession = Depends(get_db)):
    result = await db.execute(text("SELECT 1"))
    result.scalar()
    return {"status": "ok", "database": "connected"}


@router.get("/health/ready")
async def health_ready(db: AsyncSession = Depends(get_db)):
    await db.execute(text("SELECT 1"))
    import os

    from app.core.redis_client import ping_redis, redis_mode

    redis_status = "skipped"
    url = os.getenv("REDIS_URL", "")
    mode = redis_mode()
    if url or mode in ("sentinel", "cluster"):
        redis_status = ping_redis()
    status = "ok" if redis_status in ("ok", "skipped") else "degraded"
    return {
        "status": status,
        "database": "ok",
        "redis": redis_status,
        "redis_mode": mode,
    }
