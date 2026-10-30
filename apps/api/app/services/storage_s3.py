"""S3-compatible StorageProvider (MinIO / AWS S3)."""
from __future__ import annotations

import os
import uuid
from typing import BinaryIO

from pydantic import BaseModel


class ObjectMeta(BaseModel):
    key: str
    size: int
    content_type: str | None = None
    etag: str | None = None


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
            raise RuntimeError("boto3 is required for S3 storage. pip install boto3") from e
        self._client = boto3.client(
            "s3",
            endpoint_url=self.endpoint,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            region_name=self.region,
            config=Config(signature_version="s3v4"),
        )
        return self._client

    async def put(self, key: str, data: BinaryIO | bytes, content_type: str | None = None) -> ObjectMeta:
        client = self._get_client()
        body = data if isinstance(data, bytes) else data.read()
        extra = {}
        if content_type:
            extra["ContentType"] = content_type
        resp = client.put_object(Bucket=self.bucket, Key=key, Body=body, **extra)
        return ObjectMeta(
            key=key,
            size=len(body),
            content_type=content_type,
            etag=(resp.get("ETag") or "").strip('"') or None,
        )

    async def get(self, key: str) -> bytes:
        client = self._get_client()
        obj = client.get_object(Bucket=self.bucket, Key=key)
        return obj["Body"].read()

    async def delete(self, key: str) -> None:
        client = self._get_client()
        client.delete_object(Bucket=self.bucket, Key=key)

    async def signed_url(self, key: str, ttl_seconds: int = 3600) -> str:
        client = self._get_client()
        return client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=ttl_seconds,
        )

    def make_key(self, org_id: str, project_id: str, filename: str | None = None) -> str:
        ext = ""
        if filename and "." in filename:
            ext = "." + filename.rsplit(".", 1)[-1].lower()
        return f"{org_id}/{project_id}/{uuid.uuid4().hex}{ext}"
