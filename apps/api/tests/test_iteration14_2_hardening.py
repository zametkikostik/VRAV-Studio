"""Iteration 14.2 — public DTO hygiene, upload validation, storage backend honesty."""
from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from app.schemas.asset_serializers import asset_to_out, job_to_out
from app.services.storage_backend import is_local_media_backend
from app.services.upload_policy import ALLOWED_ASSET_TYPES


def test_public_asset_out_has_no_storage_key():
    asset = SimpleNamespace(
        id=uuid4(),
        project_id=uuid4(),
        scene_id=None,
        type="video",
        storage_key="org/proj/secret-object.mp4",
        filename="clip.mp4",
        mime_type="video/mp4",
        size_bytes=10,
        transcript=None,
        metadata_={
            "probe": {
                "status": "ok",
                "duration_ms": 1500,
                "video": {"width": 640, "height": 360, "fps": 24.0, "codec": "h264"},
                "audio": {"codec": "aac"},
            }
        },
    )
    data = asset_to_out(asset).model_dump()
    assert "storage_key" not in data
    assert "secret-object" not in str(data)
    assert data["duration_ms"] == 1500
    assert data["width"] == 640
    assert data["video_codec"] == "h264"


def test_public_job_out_has_no_output_key_or_paths():
    job = SimpleNamespace(
        id=uuid4(),
        organization_id=uuid4(),
        project_id=uuid4(),
        type="media.render",
        status="succeeded",
        error=None,
        created_at=None,
        result={
            "output_key": "org/proj/exports/out.mp4",
            "path": "/var/data/storage/org/proj/exports/out.mp4",
            "keyframes_count": 2,
            "probe": {"status": "ok"},
        },
    )
    data = job_to_out(job).model_dump()
    blob = str(data)
    assert "output_key" not in (data.get("result_summary") or {})
    assert "org/proj/exports" not in blob
    assert "/var/data" not in blob
    assert data["result_summary"]["keyframes_count"] == 2


def test_allowed_asset_types_constant():
    assert ALLOWED_ASSET_TYPES == frozenset({"image", "video", "audio", "model", "other"})


def test_local_backend_default():
    import os

    os.environ.pop("STORAGE_BACKEND", None)
    assert is_local_media_backend() is True
    os.environ["STORAGE_BACKEND"] = "s3"
    assert is_local_media_backend() is False
    os.environ.pop("STORAGE_BACKEND", None)


def test_upload_module_uses_spool_and_cleanup():
    from pathlib import Path

    text = (Path(__file__).resolve().parents[1] / "app/api/assets_upload.py").read_text()
    assert "SpooledTemporaryFile" in text
    assert "storage.delete" in text
    assert "ALLOWED_ASSET_TYPES" in text
    assert "data = await file.read()" not in text
