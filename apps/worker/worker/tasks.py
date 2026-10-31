"""Celery tasks for VRAV workers."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from worker.celery_app import celery_app

_API = Path(__file__).resolve().parents[2] / "api"
if str(_API) not in sys.path:
    sys.path.insert(0, str(_API))


@celery_app.task(name="vrav.ping", bind=True)
def ping(self):
    return {"ok": True, "task_id": self.request.id}


@celery_app.task(name="vrav.media.probe", bind=True)
def media_probe(self, storage_key: str, storage_root: str | None = None):
    from pathlib import Path as P

    root = P(storage_root or os.getenv("LOCAL_STORAGE_PATH", "./data/storage"))
    path = root / storage_key.lstrip("/")
    try:
        from app.services.media import probe, ffmpeg_available

        info = probe(path)
        return {
            "storage_key": storage_key,
            "ffmpeg_available": ffmpeg_available(),
            "probe": info,
            "task_id": self.request.id,
        }
    except Exception as e:
        return {"storage_key": storage_key, "error": str(e), "task_id": self.request.id}


@celery_app.task(name="vrav.gdpr.purge", bind=True)
def gdpr_purge(self, retention_days: int | None = None):
    import asyncio
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
    from app.services.gdpr import purge_soft_deleted

    days = retention_days if retention_days is not None else int(os.getenv("GDPR_RETENTION_DAYS", "30"))
    db_url = os.getenv("DATABASE_URL", "postgresql+asyncpg://vrav:vrav@localhost:5432/vrav")

    async def _run():
        engine = create_async_engine(db_url)
        Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with Session() as session:
            n = await purge_soft_deleted(session, retention_days=days)
            await session.commit()
        await engine.dispose()
        return n

    n = asyncio.run(_run())
    return {"purged": n, "retention_days": days, "task_id": self.request.id}


@celery_app.task(name="vrav.media.render", bind=True)
def media_render(
    self,
    clips: list[dict],
    output_key: str,
    storage_root: str | None = None,
    width: int = 1280,
    height: int = 720,
    fps: float = 30.0,
):
    from pathlib import Path as P

    root = P(storage_root or os.getenv("LOCAL_STORAGE_PATH", "./data/storage"))
    try:
        from app.services.media import ffmpeg_available
        from app.services.render import RenderClip, RenderRequest, render_timeline

        if not ffmpeg_available():
            return {"ok": False, "error": "ffmpeg not available", "task_id": self.request.id}

        render_clips = []
        for c in clips:
            path = root / str(c["storage_key"]).lstrip("/")
            render_clips.append(
                RenderClip(
                    path=path,
                    duration_ms=c.get("duration_ms"),
                    source_in_ms=int(c.get("source_in_ms") or 0),
                )
            )
        out = root / output_key.lstrip("/")
        result = render_timeline(
            RenderRequest(
                clips=render_clips,
                output_path=out,
                width=width,
                height=height,
                fps=fps,
            )
        )
        return {
            "ok": result.ok,
            "output_key": output_key,
            "size_bytes": result.size_bytes,
            "duration_sec": result.duration_sec,
            "error": result.error,
            "task_id": self.request.id,
        }
    except Exception as e:
        return {"ok": False, "error": str(e), "task_id": self.request.id}


@celery_app.task(name="vrav.credits.release_stale", bind=True)
def credits_release_stale(self, older_than_seconds=None):
    """Release pending credit reservations older than TTL (Celery Beat)."""
    import asyncio
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    ttl = older_than_seconds if older_than_seconds is not None else int(
        os.getenv("CREDIT_RESERVATION_TTL_SECONDS", "3600")
    )
    db_url = os.getenv("DATABASE_URL", "postgresql+asyncpg://vrav:vrav@localhost:5432/vrav")

    async def _run():
        from app.services.credits import CreditService

        engine = create_async_engine(db_url)
        Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with Session() as session:
            n = await CreditService(session).release_stale_reservations(ttl)
            await session.commit()
        await engine.dispose()
        return n

    n = asyncio.run(_run())
    return {"released": n, "ttl_seconds": ttl, "task_id": self.request.id}
