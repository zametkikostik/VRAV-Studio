"""Structured AI editing plan IR — validate before apply/render."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class PlanClip(BaseModel):
    id: str | None = None
    asset_id: str
    track_type: Literal["video", "audio", "overlay"] = "video"
    track_name: str | None = None
    source_in_ms: int = Field(default=0, ge=0)
    source_out_ms: int | None = Field(default=None, ge=0)
    timeline_start_ms: int = Field(default=0, ge=0)
    duration_ms: int = Field(gt=0)

    @model_validator(mode="after")
    def check_source_window(self) -> PlanClip:
        if self.source_out_ms is not None and self.source_out_ms <= self.source_in_ms:
            raise ValueError("source_out_ms must be greater than source_in_ms")
        if self.source_out_ms is not None:
            window = self.source_out_ms - self.source_in_ms
            if self.duration_ms > window:
                raise ValueError("duration_ms exceeds source in/out window")
        return self


class PlanSubtitle(BaseModel):
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    text: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def check_range(self) -> PlanSubtitle:
        if self.end_ms <= self.start_ms:
            raise ValueError("subtitle end_ms must be > start_ms")
        return self


class PlanOutput(BaseModel):
    width: int = Field(default=1280, ge=16, le=7680)
    height: int = Field(default=720, ge=16, le=4320)
    fps: float = Field(default=30.0, gt=0, le=120)
    video_codec: str = "libx264"
    audio_codec: str = "aac"
    container: str = "mp4"


class EditingPlan(BaseModel):
    version: str = "1.0"
    project_id: str
    source_asset_ids: list[str] = Field(default_factory=list)
    clips: list[PlanClip] = Field(default_factory=list)
    subtitles: list[PlanSubtitle] = Field(default_factory=list)
    output: PlanOutput = Field(default_factory=PlanOutput)
    notes: str | None = None

    @field_validator("version")
    @classmethod
    def version_ok(cls, v: str) -> str:
        if not v or len(v) > 32:
            raise ValueError("invalid version")
        return v

    @model_validator(mode="after")
    def clips_reference_sources(self) -> EditingPlan:
        if not self.clips:
            raise ValueError("plan must contain at least one clip")
        known = set(self.source_asset_ids)
        for c in self.clips:
            if known and c.asset_id not in known:
                raise ValueError(f"clip asset_id {c.asset_id} not in source_asset_ids")
        return self


class PlanValidationError(Exception):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


def validate_plan(data: dict[str, Any] | EditingPlan) -> EditingPlan:
    if isinstance(data, EditingPlan):
        return data
    return EditingPlan.model_validate(data)


def plan_to_render_clips(plan: EditingPlan) -> list[dict[str, Any]]:
    ordered = sorted(plan.clips, key=lambda c: (c.timeline_start_ms, c.asset_id))
    out: list[dict[str, Any]] = []
    for c in ordered:
        if c.track_type != "video":
            continue
        out.append({"asset_id": c.asset_id, "duration_ms": c.duration_ms, "source_in_ms": c.source_in_ms})
    if not out:
        raise PlanValidationError(["no video clips to render"])
    return out


def generate_mock_plan(project_id: str, assets: list[dict], *, default_clip_ms: int = 3000, gap_ms: int = 0) -> EditingPlan:
    if not assets:
        raise PlanValidationError(["no assets to build plan"])
    clips: list[PlanClip] = []
    source_ids: list[str] = []
    t = 0
    for i, a in enumerate(assets):
        aid = str(a["id"])
        atype = (a.get("type") or "other").lower()
        if atype not in ("video", "image", "other"):
            continue
        source_ids.append(aid)
        dur = int(a.get("duration_ms") or default_clip_ms)
        if dur <= 0:
            dur = default_clip_ms
        clips.append(PlanClip(id=f"clip-{i}", asset_id=aid, track_type="video", track_name="V1",
                              source_in_ms=0, timeline_start_ms=t, duration_ms=dur))
        t += dur + gap_ms
    if not clips:
        raise PlanValidationError(["no suitable assets for video plan"])
    return EditingPlan(version="1.0", project_id=project_id, source_asset_ids=source_ids, clips=clips,
                       output=PlanOutput(), notes="deterministic mock plan — not real AI analysis")
