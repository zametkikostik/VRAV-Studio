"""Iteration 14: allowlisted AssetOut / JobOut serializers."""
from types import SimpleNamespace
from uuid import uuid4

from app.schemas.asset_serializers import asset_to_out, job_to_out


def test_asset_to_out_allowlists_probe_fields():
    aid = uuid4()
    pid = uuid4()
    asset = SimpleNamespace(
        id=aid,
        project_id=pid,
        scene_id=None,
        type="video",
        storage_key="org/proj/file.mp4",
        filename="file.mp4",
        mime_type="video/mp4",
        size_bytes=100,
        transcript="hello",
        metadata_={
            "probe": {
                "status": "ok",
                "duration_ms": 5000,
                "video": {"width": 1280, "height": 720, "fps": 30.0, "codec": "h264"},
                "audio": {"codec": "aac"},
                "path": "/secret/abs/path",
            },
            "keyframes": [
                {"index": 0, "timestamp_ms": 1000, "filename": "kf_000.jpg", "path": "/secret/kf"}
            ],
            "transcription": {
                "status": "completed",
                "provider": "mock",
                "segments": [{"start_ms": 0, "end_ms": 500, "text": "hello"}],
            },
        },
    )
    out = asset_to_out(asset)
    d = out.model_dump()
    assert d["duration_ms"] == 5000
    assert d["width"] == 1280
    assert d["probe_status"] == "ok"
    assert d["transcript"] == "hello"
    assert d["keyframes"][0]["filename"] == "kf_000.jpg"
    assert "path" not in str(d["keyframes"])
    assert "/secret" not in str(d)


def test_job_to_out_strips_raw_paths():
    job = SimpleNamespace(
        id=uuid4(),
        organization_id=uuid4(),
        project_id=uuid4(),
        type="media.analyze",
        status="succeeded",
        error=None,
        created_at=None,
        result={"keyframes_count": 3, "path": "/tmp/x", "probe": {"status": "ok", "path": "/x"}},
    )
    out = job_to_out(job)
    assert out.result_summary is not None
    assert out.result_summary.keyframes_count == 3
    assert out.result_summary.probe_status == "ok"
