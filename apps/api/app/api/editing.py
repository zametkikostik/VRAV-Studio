"""Editing plan validate / apply helpers."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.models.organization import OrganizationMember
from app.models.project import Asset, Project
from app.services.editing_plan import EditingPlan, PlanValidationError, plan_to_render_clips, validate_plan

router = APIRouter(prefix="/editing", tags=["editing"])


class ValidatePlanBody(BaseModel):
    plan: dict


@router.post("/plans/validate")
async def validate_editing_plan(body: ValidatePlanBody, user: CurrentUser, db: DbSession):
    try:
        plan = validate_plan(body.plan)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        project_id = uuid.UUID(plan.project_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid project_id")

    result = await db.execute(
        select(Project)
        .join(OrganizationMember, OrganizationMember.organization_id == Project.organization_id)
        .where(
            Project.id == project_id,
            OrganizationMember.user_id == user.id,
            Project.deleted_at.is_(None),
        )
    )
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    missing: list[str] = []
    for aid in {c.asset_id for c in plan.clips}:
        try:
            asset = await db.get(Asset, uuid.UUID(aid))
        except ValueError:
            missing.append(aid)
            continue
        if asset is None or asset.project_id != project_id:
            missing.append(aid)
    if missing:
        raise HTTPException(status_code=400, detail={"missing_assets": missing})

    try:
        render_clips = plan_to_render_clips(plan)
    except PlanValidationError as e:
        raise HTTPException(status_code=400, detail=e.errors)

    return {
        "valid": True,
        "clip_count": len(plan.clips),
        "render_clip_count": len(render_clips),
        "output": plan.output.model_dump(),
        "render_clips": render_clips,
    }


class MockPlanRequest(BaseModel):
    project_id: str
    default_clip_ms: int = 3000


@router.post("/plans/mock")
async def mock_plan(body: MockPlanRequest, user: CurrentUser, db: DbSession):
    """Deterministic plan from project assets (not real AI)."""
    from app.services.editing_plan import generate_mock_plan, PlanValidationError

    try:
        project_id = uuid.UUID(body.project_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid project_id")

    result = await db.execute(
        select(Project)
        .join(OrganizationMember, OrganizationMember.organization_id == Project.organization_id)
        .where(
            Project.id == project_id,
            OrganizationMember.user_id == user.id,
            Project.deleted_at.is_(None),
        )
    )
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    assets_r = await db.execute(select(Asset).where(Asset.project_id == project_id, Asset.deleted_at.is_(None)))
    assets = assets_r.scalars().all()
    asset_dicts = [
        {"id": str(a.id), "type": a.type, "duration_ms": None, "filename": a.filename}
        for a in assets
    ]
    try:
        plan = generate_mock_plan(str(project_id), asset_dicts, default_clip_ms=body.default_clip_ms)
    except PlanValidationError as e:
        raise HTTPException(status_code=400, detail=e.errors)
    return {"plan": plan.model_dump(), "source": "mock"}


class ApplyPlanRequest(BaseModel):
    project_id: str
    timeline_id: str
    plan: dict
    replace_video_track: bool = True


@router.post("/plans/apply")
async def apply_plan(body: ApplyPlanRequest, user: CurrentUser, db: DbSession):
    """Validate plan, ensure assets, write clips onto timeline video track."""
    from app.models.timeline import Timeline
    from app.services.apply_plan import apply_plan_to_timeline
    from app.services.editing_plan import plan_to_render_clips

    try:
        project_id = uuid.UUID(body.project_id)
        timeline_id = uuid.UUID(body.timeline_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid UUID")

    result = await db.execute(
        select(Project)
        .join(OrganizationMember, OrganizationMember.organization_id == Project.organization_id)
        .where(
            Project.id == project_id,
            OrganizationMember.user_id == user.id,
            Project.deleted_at.is_(None),
        )
    )
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        plan = validate_plan(body.plan)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    if plan.project_id != str(project_id):
        raise HTTPException(status_code=400, detail="plan.project_id mismatch")

    missing: list[str] = []
    for aid in {c.asset_id for c in plan.clips}:
        try:
            asset = await db.get(Asset, uuid.UUID(aid))
        except ValueError:
            missing.append(aid)
            continue
        if asset is None or asset.project_id != project_id:
            missing.append(aid)
    if missing:
        raise HTTPException(status_code=400, detail={"missing_assets": missing})

    tl = await db.get(Timeline, timeline_id)
    if tl is None or tl.project_id != project_id:
        raise HTTPException(status_code=404, detail="Timeline not found")

    try:
        timeline = await apply_plan_to_timeline(
            db, timeline_id, plan, replace_video_track=body.replace_video_track
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    clip_count = sum(len(tr.clips or []) for tr in (timeline.tracks or []))
    return {
        "timeline_id": str(timeline.id),
        "duration_ms": timeline.duration_ms,
        "clip_count": clip_count,
        "render_clips": plan_to_render_clips(plan),
    }
