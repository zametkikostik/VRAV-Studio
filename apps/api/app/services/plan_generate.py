"""Generate EditingPlan: heuristics and optional LLM JSON with strict validation."""
from __future__ import annotations

import json
import re
from typing import Any

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
      "source_in_ms": 0
    }
  ],
  "subtitles": [],
  "output": {"width": 1280, "height": 720, "fps": 30},
  "notes": "short note"
}
Use only asset ids from the provided list. Timestamps are integer milliseconds.
"""


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


def _mock_llm_plan(project_id: str, assets: list[dict], brief: str) -> EditingPlan:
    return plan_from_brief(project_id, assets, brief or "edit video clips sequentially")


async def generate_plan_llm(
    *,
    project_id: str,
    assets: list[dict],
    brief: str,
    model: str = "mock/default",
    chat_fn: Any = None,
) -> tuple[EditingPlan, str]:
    if not assets:
        raise PlanValidationError(["no assets"])

    asset_lines = "\n".join(
        f"- id={a['id']} type={a.get('type')} file={a.get('filename') or ''}" for a in assets
    )
    user_msg = f"project_id={project_id}\nbrief:\n{brief}\n\nassets:\n{asset_lines}\n"
    provider_prefix = model.split("/", 1)[0] if model else "mock"

    if chat_fn is None and provider_prefix == "mock":
        plan = _mock_llm_plan(project_id, assets, brief)
        plan.notes = (plan.notes or "") + " | mock-llm path"
        return plan, "llm_mock"

    if chat_fn is None:
        plan = plan_from_brief(project_id, assets, brief or "edit video")
        return plan, "heuristics"

    try:
        content = await chat_fn(PLAN_JSON_INSTRUCTION, user_msg, model)
        raw = _extract_json_object(content)
        raw.setdefault("project_id", project_id)
        raw.setdefault(
            "source_asset_ids",
            [str(a["id"]) for a in assets if (a.get("type") or "") != "audio"],
        )
        plan = validate_plan(raw)
        if plan.project_id != project_id:
            raise PlanValidationError(["plan.project_id mismatch"])
        return plan, "llm"
    except Exception:
        plan = plan_from_brief(project_id, assets, brief or "edit video")
        return plan, "llm_fallback_heuristics"
