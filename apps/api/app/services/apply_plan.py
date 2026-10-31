"""Apply a validated EditingPlan onto a timeline (replace video track clips)."""
from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.timeline import Clip, Timeline, TimelineTrack
from app.services.editing_plan import EditingPlan


async def apply_plan_to_timeline(
    db: AsyncSession,
    timeline_id: uuid.UUID,
    plan: EditingPlan,
    *,
    replace_video_track: bool = True,
) -> Timeline:
    result = await db.execute(
        select(Timeline)
        .options(selectinload(Timeline.tracks).selectinload(TimelineTrack.clips))
        .where(Timeline.id == timeline_id)
    )
    timeline = result.scalar_one_or_none()
    if timeline is None:
        raise ValueError("timeline not found")

    video_tracks = [tr for tr in (timeline.tracks or []) if tr.track_type == "video"]
    if not video_tracks:
        track = TimelineTrack(id=uuid.uuid4(), timeline_id=timeline.id, name="V1", track_type="video", order_index=0)
        db.add(track)
        await db.flush()
        video_tracks = [track]
    else:
        track = sorted(video_tracks, key=lambda x: x.order_index)[0]

    if replace_video_track:
        for c in list(track.clips or []):
            await db.delete(c)
        await db.flush()

    max_end = 0
    for pc in sorted(plan.clips, key=lambda c: c.timeline_start_ms):
        if pc.track_type != "video":
            continue
        clip = Clip(
            id=uuid.uuid4(),
            track_id=track.id,
            asset_id=uuid.UUID(pc.asset_id),
            start_ms=pc.timeline_start_ms,
            duration_ms=pc.duration_ms,
            metadata_={"source_in_ms": pc.source_in_ms, "plan_clip_id": pc.id},
        )
        db.add(clip)
        max_end = max(max_end, pc.timeline_start_ms + pc.duration_ms)

    timeline.duration_ms = max(timeline.duration_ms or 0, max_end)
    if plan.output and plan.output.fps:
        timeline.fps = Decimal(str(plan.output.fps))
    await db.flush()

    result = await db.execute(
        select(Timeline)
        .options(selectinload(Timeline.tracks).selectinload(TimelineTrack.clips))
        .where(Timeline.id == timeline_id)
    )
    return result.scalar_one()
