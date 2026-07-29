"""Storage abstraction: local filesystem (dev) or S3-compatible (prod).

Selected via Settings.storage_backend. Callers never touch the filesystem
or an S3 client directly - only this interface - so swapping backends is
a config change, not a code change (see ARCHITECTURE.md §4.3).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol

from app.core.config import get_settings


class Storage(Protocol):
    def save(self, key: str, data: bytes) -> str: ...
    def open(self, key: str) -> bytes: ...
    def exists(self, key: str) -> bool: ...
    def url(self, key: str) -> str: ...


class LocalFsStorage:
    def __init__(self, root: str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if not str(p).startswith(str(self.root.resolve())):
            raise ValueError("Invalid storage key (path traversal attempt)")
        return p

    def save(self, key: str, data: bytes) -> str:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return key

    def open(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def exists(self, key: str) -> bool:
        return self._path(key).exists()

    def url(self, key: str) -> str:
        return f"/api/files/{key}"


class S3Storage:
    """Thin boto3 wrapper. Kept dependency-optional: boto3 is only imported
    if this backend is actually selected, so local dev never needs it installed.
    """

    def __init__(self, bucket: str, endpoint_url: str, access_key: str, secret_key: str, region: str) -> None:
        import boto3  # noqa: PLC0415

        self.bucket = bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint_url or None,
            aws_access_key_id=access_key or None,
            aws_secret_access_key=secret_key or None,
            region_name=region,
        )

    def save(self, key: str, data: bytes) -> str:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data)
        return key

    def open(self, key: str) -> bytes:
        obj = self.client.get_object(Bucket=self.bucket, Key=key)
        return obj["Body"].read()

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception:
            return False

    def url(self, key: str) -> str:
        return self.client.generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=3600
        )


_storage_instance: Storage | None = None


def get_storage() -> Storage:
    global _storage_instance
    if _storage_instance is not None:
        return _storage_instance

    settings = get_settings()
    if settings.storage_backend == "s3":
        _storage_instance = S3Storage(
            bucket=settings.s3_bucket,
            endpoint_url=settings.s3_endpoint_url,
            access_key=settings.s3_access_key,
            secret_key=settings.s3_secret_key,
            region=settings.s3_region,
        )
    else:
        _storage_instance = LocalFsStorage(settings.storage_local_root)
    return _storage_instance
