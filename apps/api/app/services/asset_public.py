"""Allowlisted public views of Asset / Job intelligence (no paths/secrets)."""
from __future__ import annotations

from typing import Any

from app.schemas.project import (
    AssetOut,
    JobOut,
    JobResultSummary,
    KeyframeMetaOut,
    TranscriptSegmentOut,
)


def asset_to_out(asset: Any) -> AssetOut:
    meta = getattr(asset, "metadata_", None) or {}
    if not isinstance(meta, dict):
        meta = {}
    probe = meta.get("probe") if isinstance(meta.get("probe"), dict) else {}
    video = probe.get("video") if isinstance(probe.get("video"), dict) else {}
    audio = probe.get("audio") if isinstance(probe.get("audio"), dict) else {}
    tr = meta.get("transcription") if isinstance(meta.get("transcription"), dict) else {}
    segments_raw = tr.get("segments") if isinstance(tr.get("segments"), list) else []
    segments: list[TranscriptSegmentOut] = []
    for s in segments_raw[:100]:
        if not isinstance(s, dict):
            continue
        try:
            segments.append(
                TranscriptSegmentOut(
                    start_ms=int(s.get("start_ms", 0)),
                    end_ms=int(s.get("end_ms", 0)),
                    text=str(s.get("text") or "")[:2000],
                )
            )
        except (TypeError, ValueError):
            continue
    kfs_raw = meta.get("keyframes") if isinstance(meta.get("keyframes"), list) else []
    kfs: list[KeyframeMetaOut] = []
    for k in kfs_raw[:24]:
        if not isinstance(k, dict) or not k.get("filename"):
            continue
        try:
            kfs.append(
                KeyframeMetaOut(
                    index=int(k.get("index", 0)),
                    timestamp_ms=int(k.get("timestamp_ms", 0)),
                    filename=str(k["filename"]),
                )
            )
        except (TypeError, ValueError, KeyError):
            continue
    duration = meta.get("duration_ms")
    if duration is None:
        duration = probe.get("duration_ms")
    try:
        duration_i = int(duration) if duration is not None else None
    except (TypeError, ValueError):
        duration_i = None
    return AssetOut(
        id=str(asset.id),
        project_id=str(asset.project_id),
        scene_id=str(asset.scene_id) if getattr(asset, "scene_id", None) else None,
        type=asset.type,
        storage_key=asset.storage_key,
        filename=asset.filename,
        mime_type=asset.mime_type,
        size_bytes=asset.size_bytes,
        duration_ms=duration_i,
        width=video.get("width") or meta.get("width"),
        height=video.get("height") or meta.get("height"),
        fps=video.get("fps") if video.get("fps") is not None else meta.get("fps"),
        video_codec=video.get("codec"),
        audio_codec=audio.get("codec"),
        probe_status=probe.get("status") or meta.get("probe_status"),
        transcription_status=tr.get("status"),
        transcription_provider=tr.get("provider"),
        transcript=(getattr(asset, "transcript", None) or None),
        transcript_segments=segments or None,
        keyframes=kfs or None,
    )


def job_result_summary(job: Any) -> JobResultSummary | None:
    res = getattr(job, "result", None)
    if not isinstance(res, dict):
        return None
    probe = res.get("probe") if isinstance(res.get("probe"), dict) else {}
    return JobResultSummary(
        asset_id=str(res["asset_id"]) if res.get("asset_id") else None,
        keyframes_count=res.get("keyframes_count") if isinstance(res.get("keyframes_count"), int) else None,
        status=str(res["status"]) if res.get("status") else None,
        provider=str(res["provider"]) if res.get("provider") else None,
        output_key=str(res["output_key"]) if res.get("output_key") else None,
        size_bytes=res.get("size_bytes") if isinstance(res.get("size_bytes"), int) else None,
        duration_sec=float(res["duration_sec"]) if res.get("duration_sec") is not None else None,
        probe_status=str(probe["status"]) if probe.get("status") else None,
    )


def job_to_out(job: Any) -> JobOut:
    return JobOut(
        id=str(job.id),
        organization_id=str(job.organization_id),
        project_id=str(job.project_id) if job.project_id else None,
        type=job.type,
        status=job.status,
        error=job.error,
        created_at=job.created_at.isoformat() if getattr(job, "created_at", None) else None,
        result_summary=job_result_summary(job),
    )
