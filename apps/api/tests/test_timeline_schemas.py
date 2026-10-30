from pydantic import BaseModel, Field


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


def test_timeline_create_defaults():
    t = TimelineCreate()
    assert t.name == "Main"
    assert t.fps == 30.0


def test_track_and_clip():
    tr = TrackCreate(track_type="audio", order_index=1)
    assert tr.track_type == "audio"
    c = ClipCreate(start_ms=0, duration_ms=1000)
    assert c.duration_ms == 1000
