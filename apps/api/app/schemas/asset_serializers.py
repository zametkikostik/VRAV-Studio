"""Allowlisted Asset/Job serialization — never dump raw metadata or absolute paths."""
from __future__ import annotations

from typing import Any

from app.schemas.project import (
    AssetOut,
    JobOut,
    JobResultSummary,
    KeyframeMetaOut,
    TranscriptSegmentOut,
)


def sanitize_job_error(err: str | None) -> str | None:
    """Public-safe job error: strip paths, storage keys, credentials."""
    if not err:
        return None
    text = str(err)
    low = text.lower()
    if any(
        x in low
        for x in (
            "/var/",
            "/home/",
            "/tmp/",
            "storage/",
            "s3://",
            "access_key",
            "secret",
            "password",
            "token=",
        )
    ):
        return "Processing failed (details withheld)"
    if len(text) > 240:
        return text[:240] + "…"
    return text


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
    kf_raw = meta.get("keyframes") if isinstance(meta.get("keyframes"), list) else []
    keyframes: list[KeyframeMetaOut] = []
    for k in kf_raw[:24]:
        if not isinstance(k, dict) or not k.get("filename"):
            continue
        try:
            keyframes.append(
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
        scene_id=str(asset.scene_id) if asset.scene_id else None,
        type=asset.type,
        filename=asset.filename,
        mime_type=asset.mime_type,
        size_bytes=asset.size_bytes,
        duration_ms=duration_i,
        width=video.get("width") or meta.get("width"),
        height=video.get("height") or meta.get("height"),
        fps=video.get("fps") if video.get("fps") is not None else meta.get("fps"),
        video_codec=video.get("codec"),
        audio_codec=audio.get("codec"),
        probe_status=probe.get("status"),
        transcription_status=tr.get("status"),
        transcription_provider=tr.get("provider"),
        transcript=(getattr(asset, "transcript", None) or None),
        transcript_segments=segments or None,
        keyframes=keyframes or None,
    )


def job_to_out(job: Any) -> JobOut:
    summary = None
    raw = getattr(job, "result", None)
    if isinstance(raw, dict):
        summary = JobResultSummary(
            keyframes_count=raw.get("keyframes_count") if isinstance(raw.get("keyframes_count"), int) else None,
            probe_status=(raw.get("probe") or {}).get("status")
            if isinstance(raw.get("probe"), dict)
            else None,
            chars=raw.get("chars") if isinstance(raw.get("chars"), int) else None,
            status=raw.get("status") if isinstance(raw.get("status"), str) else None,
            size_bytes=raw.get("size_bytes") if isinstance(raw.get("size_bytes"), int) else None,
            duration_sec=float(raw["duration_sec"]) if raw.get("duration_sec") is not None else None,
            queued=raw.get("queued") if isinstance(raw.get("queued"), bool) else None,
            asset_id=str(raw["asset_id"]) if raw.get("asset_id") else None,
            provider=str(raw["provider"]) if raw.get("provider") else None,
        )
    return JobOut(
        id=str(job.id),
        organization_id=str(job.organization_id),
        project_id=str(job.project_id) if job.project_id else None,
        type=job.type,
        status=job.status,
        error=sanitize_job_error(job.error),
        created_at=job.created_at.isoformat() if job.created_at else None,
        result_summary=summary,
    )
