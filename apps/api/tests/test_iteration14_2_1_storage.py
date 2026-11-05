"""Iteration 14.2.1 — S3 upload adapter, compensation, safe errors."""
from __future__ import annotations

import io
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4


def test_s3_put_uses_upload_fileobj_for_binaryio():
    from app.services.storage_s3 import S3StorageProvider, _MAX_CONCURRENCY, _MULTIPART_CHUNKSIZE

    provider = S3StorageProvider(
        endpoint="http://localhost:9000",
        access_key="x",
        secret_key="y",
        bucket="b",
    )
    mock_client = MagicMock()
    mock_client.head_object.return_value = {"ContentLength": 11, "ETag": '"abc"'}
    provider._client = mock_client

    buf = io.BytesIO(b"hello world")
    with patch("boto3.s3.transfer.TransferConfig") as TC:
        meta = provider._put_sync("org/p/k.bin", buf, content_type="application/octet-stream")
        assert mock_client.upload_fileobj.called
        call_kw = mock_client.upload_fileobj.call_args
        assert call_kw[0][1] == "b"
        assert call_kw[0][2] == "org/p/k.bin"
        extra = call_kw[1].get("ExtraArgs") or {}
        assert extra.get("ContentType") == "application/octet-stream"
        assert meta.size == 11
        assert meta.etag == "abc"
        assert TC.called
        cfg_kwargs = TC.call_args.kwargs
        assert cfg_kwargs.get("max_concurrency") == _MAX_CONCURRENCY
        assert cfg_kwargs.get("multipart_chunksize") == _MULTIPART_CHUNKSIZE


def test_s3_put_bytes_also_uses_upload_fileobj():
    from app.services.storage_s3 import S3StorageProvider

    provider = S3StorageProvider(access_key="x", secret_key="y", bucket="b")
    mock_client = MagicMock()
    mock_client.head_object.return_value = {"ContentLength": 3, "ETag": '"z"'}
    provider._client = mock_client
    meta = provider._put_sync("k", b"abc", content_type="text/plain")
    assert mock_client.upload_fileobj.called
    assert meta.size == 3
    assert mock_client.put_object.called is False


def test_sanitize_job_error_strips_paths():
    from app.schemas.asset_serializers import job_to_out, sanitize_job_error

    assert sanitize_job_error(None) is None
    assert "withheld" in (sanitize_job_error("/var/data/storage/secret.mp4 failed") or "").lower()
    job = SimpleNamespace(
        id=uuid4(),
        organization_id=uuid4(),
        project_id=None,
        type="media.analyze",
        status="failed",
        error="/home/user/.aws/credentials leaked",
        created_at=None,
        result=None,
    )
    out = job_to_out(job)
    assert out.error is not None
    assert "credentials" not in out.error.lower()
    assert "/home/" not in out.error


def test_public_asset_still_without_storage_key():
    from app.schemas.asset_serializers import asset_to_out

    asset = SimpleNamespace(
        id=uuid4(),
        project_id=uuid4(),
        scene_id=None,
        type="video",
        storage_key="hidden/key",
        filename="a.mp4",
        mime_type="video/mp4",
        size_bytes=1,
        transcript=None,
        metadata_={},
    )
    data = asset_to_out(asset).model_dump()
    assert "storage_key" not in data
    assert "hidden/key" not in str(data)


def test_session_registers_pending_keys_pattern():
    from pathlib import Path

    text = (Path(__file__).resolve().parents[1] / "app/db/session.py").read_text()
    assert "pending_storage_keys" in text
    assert "storage.delete" in text or "await storage.delete" in text


def test_create_asset_validates_scene_before_put():
    from pathlib import Path

    text = (Path(__file__).resolve().parents[1] / "app/api/projects.py").read_text()
    create = text.split("async def create_asset", 1)[1].split("@router.get", 1)[0]
    assert "Scene not found in this project" in create
    assert create.find("Scene not found") < create.find("storage.put")


def test_export_requires_local_backend():
    from pathlib import Path

    text = (Path(__file__).resolve().parents[1] / "app/api/jobs.py").read_text()
    export = text.split("async def download_export", 1)[1][:400]
    assert "_require_local_backend" in export
