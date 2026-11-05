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
        req = RenderRequest(
            clips=[RenderClip(**c) if isinstance(c, dict) else c for c in clips],
            output_key=output_key,
            storage_root=str(root),
            width=width,
            height=height,
            fps=fps,
        )
        result = render_timeline(req)
        return {"ok": True, "result": result.__dict__ if hasattr(result, "__dict__") else result, "task_id": self.request.id}
    except Exception as e:
        return {"ok": False, "error": str(e), "task_id": self.request.id}


@celery_app.task(name="vrav.media.analyze", bind=True)
def media_analyze(self, asset_id: str, storage_root: str | None = None, extract_frames: bool = True):
    """Probe asset file and persist normalized metadata (+ optional keyframes)."""
    import asyncio
    import uuid as uuid_mod
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    async def _run():
        from app.services.asset_analysis import apply_probe_to_asset

        db_url = os.getenv("DATABASE_URL")
        if not db_url:
            return {"error": "DATABASE_URL not set", "task_id": self.request.id}
        engine = create_async_engine(db_url, pool_pre_ping=True)
        Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with Session() as session:
            try:
                result = await apply_probe_to_asset(
                    session,
                    uuid_mod.UUID(asset_id),
                    storage_root=storage_root,
                    extract_frames=extract_frames,
                )
                await session.commit()
                result["task_id"] = self.request.id
                return result
            except Exception as e:
                await session.rollback()
                return {"asset_id": asset_id, "error": str(e), "task_id": self.request.id}
            finally:
                await engine.dispose()

    return asyncio.run(_run())


@celery_app.task(name="vrav.media.transcribe", bind=True)
def media_transcribe(self, asset_id: str, storage_root: str | None = None):
    """Run transcription provider and persist text/segments (mock in CI)."""
    import asyncio
    import uuid as uuid_mod
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from app.services.media import resolve_storage_path
    from app.services.transcription import get_transcription_provider
    from app.services.asset_analysis import apply_transcript_to_asset

    async def _run():
        db_url = os.getenv("DATABASE_URL")
        if not db_url:
            return {"error": "DATABASE_URL not set", "task_id": self.request.id}
        engine = create_async_engine(db_url, pool_pre_ping=True)
        Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with Session() as session:
            try:
                from app.models.project import Asset

                asset = await session.get(Asset, uuid_mod.UUID(asset_id))
                if asset is None:
                    return {"error": "asset not found", "task_id": self.request.id}
                path = resolve_storage_path(asset.storage_key, storage_root)
                provider = get_transcription_provider()
                result = await provider.transcribe(audio_path=str(path))
                out = await apply_transcript_to_asset(
                    session,
                    uuid_mod.UUID(asset_id),
                    text=result["text"],
                    segments=result.get("segments"),
                    provider=result.get("provider", "mock"),
                )
                await session.commit()
                out["task_id"] = self.request.id
                return out
            except Exception as e:
                await session.rollback()
                return {"asset_id": asset_id, "error": str(e), "task_id": self.request.id}
            finally:
                await engine.dispose()

    return asyncio.run(_run())
