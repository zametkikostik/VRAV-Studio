"""Generate EditingPlan via AI Gateway JSON + strict server validation.

Never invents asset IDs. Never silently substitutes heuristics for a failed
real-provider call (only explicit mock mode may use deterministic mock plans).
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable, Awaitable

from app.services.editing_plan import (
    EditingPlan,
    PlanValidationError,
    plan_from_brief,
    validate_plan,
)

PLAN_JSON_INSTRUCTION = """You are a video editing planner. Reply with ONLY one JSON object (no markdown), schema:
{
  "version": "1.0",
  "project_id": "<uuid>",
  "source_asset_ids": ["<asset uuid>", ...],
  "clips": [
    {
      "asset_id": "<uuid from list>",
      "track_type": "video",
      "timeline_start_ms": 0,
      "duration_ms": 3000,
      "source_in_ms": 0,
      "source_out_ms": 3000,
      "effects": {}
    }
  ],
  "subtitles": [],
  "output": {"width": 1280, "height": 720, "fps": 30},
  "notes": "short note"
}
Rules:
- Use ONLY asset ids from the provided list. Never invent ids.
- Timestamps are integer milliseconds.
- source_out_ms must be <= asset duration_ms when duration_ms is provided.
- If transcript is missing for an asset, do not invent dialogue quotes.
- Prefer video/image assets for video track; audio for audio track.
"""

ChatFn = Callable[[str, str, str], Awaitable[str]]

MAX_CLIPS = 40
MAX_PLAN_DURATION_MS = 30 * 60 * 1000  # 30 minutes


def _extract_json_object(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    if not text:
        raise PlanValidationError(["empty model response"])
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            data = json.loads(text[start : end + 1])
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError as e:
            raise PlanValidationError([f"invalid JSON: {e}"]) from e
    raise PlanValidationError(["no JSON object in model response"])


def asset_context_line(a: dict[str, Any]) -> str:
    dur = a.get("duration_ms")
    dur_s = f"duration_ms={dur}" if dur is not None else "duration_ms=unknown"
    res = ""
    if a.get("width") and a.get("height"):
        res = f" resolution={a['width']}x{a['height']}"
    fps = a.get("fps")
    fps_s = f" fps={fps}" if fps is not None else ""
    tr = (a.get("transcript") or "").strip()
    if tr:
        snippet = tr[:400].replace("\n", " ")
        tr_s = f'transcript_snippet="{snippet}"'
    else:
        tr_s = "transcript=unavailable"
    kf = a.get("keyframes") or []
    kf_s = f" keyframes={len(kf)}" if kf else " keyframes=none"
    return (
        f"- id={a['id']} type={a.get('type')} file={a.get('filename') or ''} "
        f"{dur_s}{res}{fps_s} {tr_s}{kf_s}"
    )


def enforce_plan_limits(plan: EditingPlan) -> None:
    if len(plan.clips) > MAX_CLIPS:
        raise PlanValidationError([f"too many clips: {len(plan.clips)} > {MAX_CLIPS}"])
    max_end = 0
    for c in plan.clips:
        max_end = max(max_end, c.timeline_start_ms + c.duration_ms)
    if max_end > MAX_PLAN_DURATION_MS:
        raise PlanValidationError(
            [f"plan duration {max_end}ms exceeds limit {MAX_PLAN_DURATION_MS}ms"]
        )


def enforce_asset_membership(plan: EditingPlan, assets: list[dict[str, Any]]) -> None:
    known = {str(a["id"]) for a in assets}
    if not known:
        raise PlanValidationError(["no assets"])
    for c in plan.clips:
        if c.asset_id not in known:
            raise PlanValidationError([f"clip asset_id not in project: {c.asset_id}"])
    for aid in plan.source_asset_ids:
        if aid not in known:
            raise PlanValidationError([f"source_asset_id not in project: {aid}"])


def enforce_source_windows(plan: EditingPlan, assets: list[dict[str, Any]]) -> None:
    by_id = {str(a["id"]): a for a in assets}
    for c in plan.clips:
        a = by_id.get(c.asset_id)
        if not a:
            raise PlanValidationError([f"unknown asset {c.asset_id}"])
        dur = a.get("duration_ms")
        if dur is None:
            continue
        try:
            dur_i = int(dur)
        except (TypeError, ValueError):
            continue
        if c.source_in_ms > dur_i:
            raise PlanValidationError(
                [f"source_in_ms {c.source_in_ms} exceeds asset duration {dur_i} for {c.asset_id}"]
            )
        if c.source_out_ms is not None and c.source_out_ms > dur_i:
            raise PlanValidationError(
                [f"source_out_ms {c.source_out_ms} exceeds asset duration {dur_i} for {c.asset_id}"]
            )
        if c.source_out_ms is None and c.source_in_ms + c.duration_ms > dur_i:
            raise PlanValidationError(
                [f"clip duration from source_in exceeds asset duration for {c.asset_id}"]
            )


def build_limitations(assets: list[dict[str, Any]]) -> list[str]:
    notes: list[str] = []
    if not assets:
        notes.append("no_assets")
        return notes
    missing_tr = [str(a["id"]) for a in assets if not (a.get("transcript") or "").strip()]
    missing_dur = [str(a["id"]) for a in assets if a.get("duration_ms") is None]
    if missing_tr:
        notes.append(
            "transcript_unavailable_for_some_assets: planning without dialogue quotes for those ids"
        )
    if missing_dur:
        notes.append(
            "duration_unknown_for_some_assets: source out-point bounds partially enforced"
        )
    notes.append("no_visual_frame_analysis")
    return notes


async def generate_plan_llm(
    *,
    project_id: str,
    assets: list[dict],
    brief: str,
    model: str = "mock/default",
    chat_fn: ChatFn | None = None,
) -> tuple[EditingPlan, str]:
    if not assets:
        raise PlanValidationError(["no assets"])

    asset_lines = "\n".join(asset_context_line(a) for a in assets)
    limitations = build_limitations(assets)
    user_msg = (
        f"project_id={project_id}\nbrief:\n{brief}\n\nassets:\n{asset_lines}\n\n"
        f"limitations:\n" + "\n".join(f"- {x}" for x in limitations) + "\n"
    )
    provider_prefix = model.split("/", 1)[0] if model else "mock"

    if chat_fn is None and provider_prefix == "mock":
        plan = plan_from_brief(project_id, assets, brief or "edit video clips sequentially")
        enforce_plan_limits(plan)
        enforce_asset_membership(plan, assets)
        plan.notes = ((plan.notes or "") + " | mock-llm path").strip(" |")
        return plan, "llm_mock"

    if chat_fn is None:
        raise PlanValidationError(
            ["provider_unavailable: no chat_fn and model is not mock/*"]
        )

    try:
        content = await chat_fn(PLAN_JSON_INSTRUCTION, user_msg, model)
    except PlanValidationError:
        raise
    except Exception as e:
        raise PlanValidationError([f"provider_error: {type(e).__name__}: {e}"]) from e

    raw = _extract_json_object(content)
    raw.setdefault("project_id", project_id)
    raw.setdefault(
        "source_asset_ids",
        [str(a["id"]) for a in assets if (a.get("type") or "") != "audio"],
    )
    try:
        plan = validate_plan(raw)
    except Exception as e:
        raise PlanValidationError([f"malformed_plan: {e}"]) from e

    if plan.project_id != project_id:
        raise PlanValidationError(["plan.project_id mismatch"])

    enforce_plan_limits(plan)
    enforce_asset_membership(plan, assets)
    enforce_source_windows(plan, assets)
    return plan, "llm"


def duration_ms_from_asset_row(asset: Any) -> int | None:
    """Extract duration_ms from Asset.metadata_ (probe) without inventing values."""
    meta = getattr(asset, "metadata_", None) or {}
    if not isinstance(meta, dict):
        return None
    probe = meta.get("probe") if isinstance(meta.get("probe"), dict) else {}
    for key in ("duration_ms", "durationMs", "length_ms"):
        for src in (meta, probe):
            if key in src and src[key] is not None:
                try:
                    return max(0, int(src[key]))
                except (TypeError, ValueError):
                    pass
    if meta.get("duration") is not None:
        try:
            d = float(meta["duration"])
            if d < 1000:
                return int(d * 1000)
            return int(d)
        except (TypeError, ValueError):
            pass
    return None


def asset_row_to_context(asset: Any) -> dict[str, Any]:
    meta = getattr(asset, "metadata_", None) or {}
    if not isinstance(meta, dict):
        meta = {}
    probe = meta.get("probe") if isinstance(meta.get("probe"), dict) else {}
    video = probe.get("video") if isinstance(probe.get("video"), dict) else {}
    audio = probe.get("audio") if isinstance(probe.get("audio"), dict) else {}
    tr_meta = meta.get("transcription") if isinstance(meta.get("transcription"), dict) else {}
    segments = tr_meta.get("segments") if isinstance(tr_meta.get("segments"), list) else []
    keyframes = meta.get("keyframes") if isinstance(meta.get("keyframes"), list) else []
    return {
        "id": str(asset.id),
        "type": asset.type,
        "filename": asset.filename,
        "duration_ms": duration_ms_from_asset_row(asset),
        "transcript": getattr(asset, "transcript", None),
        "mime_type": getattr(asset, "mime_type", None),
        "width": video.get("width") or meta.get("width"),
        "height": video.get("height") or meta.get("height"),
        "fps": video.get("fps") or meta.get("fps"),
        "video_codec": video.get("codec"),
        "audio_codec": audio.get("codec"),
        "transcript_segments": segments[:40],
        "keyframes": keyframes[:12],
        "probe_status": probe.get("status") or meta.get("probe_status"),
    }
