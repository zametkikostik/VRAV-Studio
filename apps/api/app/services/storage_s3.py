"""S3-compatible StorageProvider (MinIO / AWS S3) with bounded-memory uploads."""
from __future__ import annotations

import asyncio
import io
import os
import uuid
from typing import BinaryIO

from pydantic import BaseModel


class ObjectMeta(BaseModel):
    key: str
    size: int
    content_type: str | None = None
    etag: str | None = None


_MULTIPART_THRESHOLD = 8 * 1024 * 1024
_MULTIPART_CHUNKSIZE = 8 * 1024 * 1024
_MAX_CONCURRENCY = 4


class S3StorageProvider:
    def __init__(
        self,
        endpoint: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        bucket: str | None = None,
        region: str = "us-east-1",
    ):
        self.endpoint = endpoint or os.getenv("S3_ENDPOINT", "http://localhost:9000")
        self.access_key = access_key or os.getenv("S3_ACCESS_KEY", "minioadmin")
        self.secret_key = secret_key or os.getenv("S3_SECRET_KEY", "minioadmin")
        self.bucket = bucket or os.getenv("S3_BUCKET", "vrav")
        self.region = region
        self._client = None

    def _get_client(self):
        if self._client is not None:
            return self._client
        try:
            import boto3
            from botocore.client import Config
        except ImportError as e:
            raise RuntimeError("boto3 is required for S3 storage") from e
        self._client = boto3.client(
            "s3",
            endpoint_url=self.endpoint,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            region_name=self.region,
            config=Config(signature_version="s3v4"),
        )
        return self._client

    def _transfer_config(self):
        from boto3.s3.transfer import TransferConfig

        return TransferConfig(
            multipart_threshold=_MULTIPART_THRESHOLD,
            multipart_chunksize=_MULTIPART_CHUNKSIZE,
            max_concurrency=_MAX_CONCURRENCY,
            use_threads=True,
        )

    def _size_of(self, data: BinaryIO | bytes) -> int:
        if isinstance(data, bytes):
            return len(data)
        if hasattr(data, "seek") and hasattr(data, "tell"):
            pos = data.tell()
            data.seek(0, io.SEEK_END)
            end = data.tell()
            data.seek(pos)
            return max(0, end - pos)
        return 0

    def _put_sync(self, key: str, data: BinaryIO | bytes, content_type: str | None) -> ObjectMeta:
        client = self._get_client()
        extra: dict = {}
        if content_type:
            extra["ContentType"] = content_type
        config = self._transfer_config()

        if isinstance(data, bytes):
            body = io.BytesIO(data)
            size = len(data)
            client.upload_fileobj(
                body,
                self.bucket,
                key,
                ExtraArgs=extra or None,
                Config=config,
            )
        else:
            if hasattr(data, "seek"):
                data.seek(0)
            size = self._size_of(data)
            if hasattr(data, "seek"):
                data.seek(0)
            client.upload_fileobj(
                data,
                self.bucket,
                key,
                ExtraArgs=extra or None,
                Config=config,
            )
            if size <= 0:
                try:
                    head = client.head_object(Bucket=self.bucket, Key=key)
                    size = int(head.get("ContentLength") or 0)
                except Exception:
                    size = 0

        etag = None
        try:
            head = client.head_object(Bucket=self.bucket, Key=key)
            etag = (head.get("ETag") or "").strip('"') or None
            if size <= 0:
                size = int(head.get("ContentLength") or 0)
        except Exception:
            pass
        return ObjectMeta(key=key, size=size, content_type=content_type, etag=etag)

    async def put(self, key: str, data: BinaryIO | bytes, content_type: str | None = None) -> ObjectMeta:
        return await asyncio.to_thread(self._put_sync, key, data, content_type)

    async def get(self, key: str) -> bytes:
        def _get():
            client = self._get_client()
            obj = client.get_object(Bucket=self.bucket, Key=key)
            return obj["Body"].read()

        return await asyncio.to_thread(_get)

    async def delete(self, key: str) -> None:
        def _del():
            client = self._get_client()
            client.delete_object(Bucket=self.bucket, Key=key)

        await asyncio.to_thread(_del)

    async def signed_url(self, key: str, ttl_seconds: int = 3600) -> str:
        def _url():
            client = self._get_client()
            return client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": key},
                ExpiresIn=ttl_seconds,
            )

        return await asyncio.to_thread(_url)

    def make_key(self, org_id: str, project_id: str, filename: str | None = None) -> str:
        ext = ""
        if filename and "." in filename:
            ext = "." + filename.rsplit(".", 1)[-1].lower()
        return f"{org_id}/{project_id}/{uuid.uuid4().hex}{ext}"
