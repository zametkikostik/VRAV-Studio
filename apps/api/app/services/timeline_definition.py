"""TimelineDefinition — strict JSON contract for the AI director / compiler.

Builds on EditingPlan (same IR). AI fills this structure; the compiler turns
it into argument-vector FFmpeg commands — never a shell string.
"""
from __future__ import annotations

from typing import Any

from app.services.editing_plan import (
    EditingPlan,
    PlanClip,
    PlanOutput,
    PlanSubtitle,
    validate_plan,
)

# Public aliases for the AI director contract
TimelineClip = PlanClip
TimelineSubtitle = PlanSubtitle
TimelineOutput = PlanOutput


class TimelineDefinition(EditingPlan):
    """AI-director timeline IR (versioned JSON schema)."""

    version: str = "1.0"


def validate_timeline(data: dict[str, Any] | TimelineDefinition | EditingPlan) -> TimelineDefinition:
    if isinstance(data, TimelineDefinition):
        return data
    plan = validate_plan(data if not isinstance(data, EditingPlan) else data.model_dump())
    return TimelineDefinition.model_validate(plan.model_dump())


def timeline_json_schema() -> dict[str, Any]:
    """JSON Schema for LLM structured output / OpenAPI docs."""
    return TimelineDefinition.model_json_schema()


def editing_plan_to_timeline(plan: EditingPlan) -> TimelineDefinition:
    return TimelineDefinition.model_validate(plan.model_dump())
