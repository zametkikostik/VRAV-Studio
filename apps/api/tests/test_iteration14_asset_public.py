"""Iteration 14: allowlisted AssetOut / JobOut serializers."""
from types import SimpleNamespace
from uuid import uuid4

from app.schemas.asset_serializers import asset_to_out, job_to_out


def test_asset_to_out_allowlist_no_paths():
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
            },
            "keyframes": [
                {"index": 0, "timestamp_ms": 1000, "filename": "kf_000.jpg", "path": "/secret/path"}
            ],
            "transcription": {
                "status": "completed",
                "provider": "mock",
                "segments": [{"start_ms": 0, "end_ms": 500, "text": "hello"}],
            },
        },
    )
    out = asset_to_out(asset)
    data = out.model_dump()
    assert data["duration_ms"] == 5000
    assert data["width"] == 1280
    assert data["video_codec"] == "h264"
    assert data["transcript"] == "hello"
    assert data["keyframes"][0]["filename"] == "kf_000.jpg"
    assert "path" not in data["keyframes"][0]
    assert "/secret" not in str(data)


def test_job_to_out_strips_unsafe_result():
    job = SimpleNamespace(
        id=uuid4(),
        organization_id=uuid4(),
        project_id=uuid4(),
        type="media.analyze",
        status="succeeded",
        error=None,
        created_at=None,
        result={
            "asset_id": str(uuid4()),
            "keyframes_count": 3,
            "path": "/var/data/secret",
            "probe": {"status": "ok"},
        },
    )
    out = job_to_out(job)
    assert out.result_summary is not None
    assert out.result_summary.keyframes_count == 3
    assert out.result_summary.probe_status == "ok"
    assert "/var/data" not in str(out.model_dump())
