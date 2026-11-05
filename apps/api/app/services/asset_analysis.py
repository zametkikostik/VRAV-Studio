"""Apply media intelligence results to Asset rows (probe / keyframes / transcript)."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Asset
from app.services.media import (
    extract_keyframes,
    merge_probe_metadata,
    normalize_probe,
    probe,
    resolve_storage_path,
)


async def apply_probe_to_asset(
    db: AsyncSession,
    asset_id: uuid.UUID,
    *,
    storage_root: str | None = None,
    extract_frames: bool = False,
    max_frames: int = 6,
) -> dict[str, Any]:
    asset = await db.get(Asset, asset_id)
    if asset is None:
        raise ValueError("asset not found")
    path = resolve_storage_path(asset.storage_key, storage_root)
    raw = probe(path)
    normalized = normalize_probe(raw)
    meta = merge_probe_metadata(asset.metadata_, normalized)
    keyframes: list[dict[str, Any]] = []
    if extract_frames and (normalized.get("video") or {}).get("width"):
        out_dir = path.parent / f".kf_{asset.id.hex[:12]}"
        try:
            keyframes = extract_keyframes(
                path, out_dir, max_frames=max_frames, duration_ms=normalized.get("duration_ms")
            )
            meta["keyframes"] = [
                {"index": k["index"], "timestamp_ms": k["timestamp_ms"], "filename": k["filename"]}
                for k in keyframes
            ]
        except Exception as e:
            meta["keyframes_error"] = type(e).__name__
    asset.metadata_ = meta
    await db.flush()
    return {"asset_id": str(asset.id), "probe": normalized, "keyframes_count": len(keyframes)}


async def apply_transcript_to_asset(
    db: AsyncSession,
    asset_id: uuid.UUID,
    *,
    text: str,
    segments: list[dict[str, Any]] | None = None,
    provider: str = "mock",
) -> dict[str, Any]:
    """Persist transcript text + optional timestamped segments. Never invents text."""
    if not (text or "").strip():
        raise ValueError("empty transcript")
    asset = await db.get(Asset, asset_id)
    if asset is None:
        raise ValueError("asset not found")
    asset.transcript = text.strip()
    meta = dict(asset.metadata_ or {})
    meta["transcription"] = {
        "status": "completed",
        "provider": provider,
        "segments": segments or [],
    }
    asset.metadata_ = meta
    await db.flush()
    return {"asset_id": str(asset.id), "status": "completed", "chars": len(asset.transcript)}
