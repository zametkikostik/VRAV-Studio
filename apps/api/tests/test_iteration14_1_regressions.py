"""Iteration 14.1 — API compatibility and upload safety regressions."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_projects_source_has_delete_and_draft_and_scene_order():
    text = (ROOT / "app/api/projects.py").read_text()
    assert '@router.delete("/projects/{project_id}"' in text
    assert 'status="draft"' in text
    assert "order_by(Scene.order_index)" in text
    assert 'await storage.put(key, b""' in text
    assert "asset_to_out" in text


def test_upload_enforces_size_while_chunking():
    text = (ROOT / "app/api/assets_upload.py").read_text()
    assert "while True:" in text
    assert "chunk = await file.read(" in text
    assert "total > max_bytes" in text
    assert "allowed_prefixes" in text
    # no unbounded single-shot read of the whole body
    assert "data = await file.read()" not in text


def test_keyframe_endpoint_rejects_non_local_backend():
    text = (ROOT / "app/api/asset_keyframes.py").read_text()
    assert "STORAGE_BACKEND" in text
    assert "501" in text
    assert "DEFERRED" in text


def test_serializer_still_allowlists():
    from types import SimpleNamespace
    from uuid import uuid4
    from app.schemas.asset_serializers import asset_to_out, job_to_out

    asset = SimpleNamespace(
        id=uuid4(),
        project_id=uuid4(),
        scene_id=None,
        type="video",
        storage_key="k",
        filename="a.mp4",
        mime_type="video/mp4",
        size_bytes=1,
        transcript=None,
        metadata_={"probe": {"status": "ok", "duration_ms": 1000, "video": {}, "audio": {}}},
    )
    out = asset_to_out(asset)
    assert out.duration_ms == 1000
    job = SimpleNamespace(
        id=uuid4(),
        organization_id=uuid4(),
        project_id=None,
        type="media.analyze",
        status="failed",
        error="x",
        created_at=None,
        result={"path": "/secret", "keyframes_count": 1},
    )
    j = job_to_out(job)
    assert "/secret" not in str(j.model_dump())
