import secrets
import uuid
from decimal import Decimal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, DbSession
from app.models.organization import OrganizationMember
from app.models.project import Project
from app.models.timeline import Clip, CollabEvent, CollabSession, Timeline, TimelineTrack

router = APIRouter(tags=["timelines"])


class TimelineCreate(BaseModel):
    name: str = "Main"
    fps: float = 30.0


class TrackCreate(BaseModel):
    name: str = "Track"
    track_type: str = Field(default="video", pattern=r"^(video|audio|overlay)$")
    order_index: int = 0


class ClipCreate(BaseModel):
    asset_id: str | None = None
    start_ms: int = Field(ge=0)
    duration_ms: int = Field(gt=0)
    metadata: dict | None = None


class ClipOut(BaseModel):
    id: str
    track_id: str
    asset_id: str | None
    start_ms: int
    duration_ms: int
    metadata: dict | None = None


class TrackOut(BaseModel):
    id: str
    name: str
    track_type: str
    order_index: int
    clips: list[ClipOut] = []


class TimelineOut(BaseModel):
    id: str
    project_id: str
    name: str
    duration_ms: int
    fps: float
    tracks: list[TrackOut] = []


async def _project_for_read(db, user_id, project_id) -> Project:
    """Timeline/collab read: project:read (viewer+)."""
    from app.services.rbac import Permission, require_project_permission
    return await require_project_permission(db, user_id, project_id, Permission.PROJECT_READ)


async def _project_for_write(db, user_id, project_id) -> Project:
    """Timeline/collab mutation: project:update (editor+)."""
    from app.services.rbac import Permission, require_project_permission
    return await require_project_permission(db, user_id, project_id, Permission.PROJECT_UPDATE)


def _timeline_out(t: Timeline) -> TimelineOut:
    tracks = []
    for tr in sorted(t.tracks or [], key=lambda x: x.order_index):
        clips = [
            ClipOut(
                id=str(c.id),
                track_id=str(c.track_id),
                asset_id=str(c.asset_id) if c.asset_id else None,
                start_ms=c.start_ms,
                duration_ms=c.duration_ms,
                metadata=c.metadata_,
            )
            for c in (tr.clips or [])
        ]
        tracks.append(
            TrackOut(
                id=str(tr.id),
                name=tr.name,
                track_type=tr.track_type,
                order_index=tr.order_index,
                clips=clips,
            )
        )
    return TimelineOut(
        id=str(t.id),
        project_id=str(t.project_id),
        name=t.name,
        duration_ms=t.duration_ms,
        fps=float(t.fps),
        tracks=tracks,
    )


@router.post("/projects/{project_id}/timelines", response_model=TimelineOut, status_code=201)
async def create_timeline(project_id: uuid.UUID, body: TimelineCreate, user: CurrentUser, db: DbSession):
    await _project_for_write(db, user.id, project_id)
    t = Timeline(
        id=uuid.uuid4(),
        project_id=project_id,
        name=body.name,
        fps=Decimal(str(body.fps)),
    )
    db.add(t)
    await db.flush()
    for i, (name, tt) in enumerate([("Video 1", "video"), ("Audio 1", "audio")]):
        db.add(TimelineTrack(id=uuid.uuid4(), timeline_id=t.id, name=name, track_type=tt, order_index=i))
    await db.flush()
    result = await db.execute(
        select(Timeline).options(selectinload(Timeline.tracks).selectinload(TimelineTrack.clips)).where(Timeline.id == t.id)
    )
    return _timeline_out(result.scalar_one())


@router.get("/projects/{project_id}/timelines", response_model=list[TimelineOut])
async def list_timelines(project_id: uuid.UUID, user: CurrentUser, db: DbSession):
    await _project_for_read(db, user.id, project_id)
    result = await db.execute(
        select(Timeline)
        .options(selectinload(Timeline.tracks).selectinload(TimelineTrack.clips))
        .where(Timeline.project_id == project_id)
    )
    return [_timeline_out(t) for t in result.scalars().all()]


@router.get("/timelines/{timeline_id}", response_model=TimelineOut)
async def get_timeline(timeline_id: uuid.UUID, user: CurrentUser, db: DbSession):
    result = await db.execute(
        select(Timeline)
        .options(selectinload(Timeline.tracks).selectinload(TimelineTrack.clips))
        .where(Timeline.id == timeline_id)
    )
    t = result.scalar_one_or_none()
    if t is None:
        raise HTTPException(status_code=404, detail="Timeline not found")
    await _project_for_read(db, user.id, t.project_id)
    return _timeline_out(t)


@router.post("/timelines/{timeline_id}/tracks", response_model=TrackOut, status_code=201)
async def add_track(timeline_id: uuid.UUID, body: TrackCreate, user: CurrentUser, db: DbSession):
    t = await db.get(Timeline, timeline_id)
    if t is None:
        raise HTTPException(status_code=404, detail="Timeline not found")
    await _project_for_write(db, user.id, t.project_id)
    tr = TimelineTrack(
        id=uuid.uuid4(), timeline_id=timeline_id, name=body.name,
        track_type=body.track_type, order_index=body.order_index,
    )
    db.add(tr)
    await db.flush()
    return TrackOut(id=str(tr.id), name=tr.name, track_type=tr.track_type, order_index=tr.order_index, clips=[])


@router.post("/tracks/{track_id}/clips", response_model=ClipOut, status_code=201)
async def add_clip(track_id: uuid.UUID, body: ClipCreate, user: CurrentUser, db: DbSession):
    tr = await db.get(TimelineTrack, track_id)
    if tr is None:
        raise HTTPException(status_code=404, detail="Track not found")
    t = await db.get(Timeline, tr.timeline_id)
    await _project_for_write(db, user.id, t.project_id)
    asset_id = uuid.UUID(body.asset_id) if body.asset_id else None
    clip = Clip(
        id=uuid.uuid4(), track_id=track_id, asset_id=asset_id,
        start_ms=body.start_ms, duration_ms=body.duration_ms, metadata_=body.metadata,
    )
    db.add(clip)
    end = body.start_ms + body.duration_ms
    if t and end > t.duration_ms:
        t.duration_ms = end
    await db.flush()
    return ClipOut(
        id=str(clip.id), track_id=str(clip.track_id),
        asset_id=str(clip.asset_id) if clip.asset_id else None,
        start_ms=clip.start_ms, duration_ms=clip.duration_ms, metadata=clip.metadata_,
    )


class CollabCreate(BaseModel):
    project_id: str


class CollabEventIn(BaseModel):
    event_type: str
    payload: dict | None = None


@router.post("/collab/sessions", status_code=201)
async def create_collab_session(body: CollabCreate, user: CurrentUser, db: DbSession):
    project_id = uuid.UUID(body.project_id)
    await _project_for_write(db, user.id, project_id)
    room_id = secrets.token_urlsafe(12)
    sess = CollabSession(
        id=uuid.uuid4(), project_id=project_id, room_id=room_id,
        created_by=user.id, status="active",
    )
    db.add(sess)
    await db.flush()
    return {"session_id": str(sess.id), "room_id": room_id, "project_id": str(project_id)}


@router.post("/collab/sessions/{session_id}/events", status_code=201)
async def append_collab_event(session_id: uuid.UUID, body: CollabEventIn, user: CurrentUser, db: DbSession):
    sess = await db.get(CollabSession, session_id)
    if sess is None or sess.status != "active":
        raise HTTPException(status_code=404, detail="Session not found")
    await _project_for_write(db, user.id, sess.project_id)
    ev = CollabEvent(session_id=session_id, user_id=user.id, event_type=body.event_type, payload=body.payload)
    db.add(ev)
    await db.flush()
    return {"event_id": ev.id, "created_at": ev.created_at.isoformat() if ev.created_at else None}


@router.get("/collab/sessions/{session_id}/events")
async def list_collab_events(session_id: uuid.UUID, user: CurrentUser, db: DbSession, after_id: int = 0):
    sess = await db.get(CollabSession, session_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="Session not found")
    await _project_for_read(db, user.id, sess.project_id)
    result = await db.execute(
        select(CollabEvent)
        .where(CollabEvent.session_id == session_id, CollabEvent.id > after_id)
        .order_by(CollabEvent.id).limit(500)
    )
    return [
        {
            "id": e.id, "user_id": str(e.user_id), "event_type": e.event_type,
            "payload": e.payload,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in result.scalars().all()
    ]


class ClipUpdate(BaseModel):
    start_ms: int | None = Field(default=None, ge=0)
    duration_ms: int | None = Field(default=None, gt=0)
    asset_id: str | None = None


@router.patch("/clips/{clip_id}", response_model=ClipOut)
async def update_clip(clip_id: uuid.UUID, body: ClipUpdate, user: CurrentUser, db: DbSession):
    clip = await db.get(Clip, clip_id)
    if clip is None:
        raise HTTPException(status_code=404, detail="Clip not found")
    tr = await db.get(TimelineTrack, clip.track_id)
    t = await db.get(Timeline, tr.timeline_id)
    await _project_for_write(db, user.id, t.project_id)
    if body.start_ms is not None:
        clip.start_ms = body.start_ms
    if body.duration_ms is not None:
        clip.duration_ms = body.duration_ms
    if body.asset_id is not None:
        clip.asset_id = uuid.UUID(body.asset_id) if body.asset_id else None
    end = clip.start_ms + clip.duration_ms
    if end > t.duration_ms:
        t.duration_ms = end
    await db.flush()
    return ClipOut(
        id=str(clip.id), track_id=str(clip.track_id),
        asset_id=str(clip.asset_id) if clip.asset_id else None,
        start_ms=clip.start_ms, duration_ms=clip.duration_ms, metadata=clip.metadata_,
    )


@router.delete("/clips/{clip_id}", status_code=204)
async def delete_clip(clip_id: uuid.UUID, user: CurrentUser, db: DbSession):
    clip = await db.get(Clip, clip_id)
    if clip is None:
        raise HTTPException(status_code=404, detail="Clip not found")
    tr = await db.get(TimelineTrack, clip.track_id)
    t = await db.get(Timeline, tr.timeline_id)
    await _project_for_write(db, user.id, t.project_id)
    await db.delete(clip)
    await db.flush()
