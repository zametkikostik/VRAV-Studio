"""Storage provider factory: local FS or S3/MinIO."""
from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import BinaryIO

from pydantic import BaseModel


class ObjectMeta(BaseModel):
    key: str
    size: int
    content_type: str | None = None
    etag: str | None = None


class LocalStorageProvider:
    def __init__(self, root: str | None = None):
        self.root = Path(root or os.getenv("LOCAL_STORAGE_PATH", "./data/storage"))
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        safe = key.lstrip("/").replace("..", "")
        return self.root / safe

    async def put(self, key: str, data: BinaryIO | bytes, content_type: str | None = None) -> ObjectMeta:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(data, bytes):
            path.write_bytes(data)
            size = len(data)
        else:
            content = data.read()
            path.write_bytes(content)
            size = len(content)
        return ObjectMeta(key=key, size=size, content_type=content_type)

    async def get(self, key: str) -> bytes:
        path = self._path(key)
        if not path.exists():
            raise FileNotFoundError(key)
        return path.read_bytes()

    async def delete(self, key: str) -> None:
        path = self._path(key)
        if path.exists():
            path.unlink()

    async def signed_url(self, key: str, ttl_seconds: int = 3600) -> str:
        return f"file://{self._path(key)}"

    def make_key(self, org_id: str, project_id: str, filename: str | None = None) -> str:
        ext = ""
        if filename and "." in filename:
            ext = "." + filename.rsplit(".", 1)[-1].lower()
        return f"{org_id}/{project_id}/{uuid.uuid4().hex}{ext}"


_storage = None


def get_storage():
    global _storage
    if _storage is not None:
        return _storage
    backend = os.getenv("STORAGE_BACKEND", "local").lower()
    if backend in ("s3", "minio"):
        from app.services.storage_s3 import S3StorageProvider

        _storage = S3StorageProvider()
    else:
        _storage = LocalStorageProvider()
    return _storage
