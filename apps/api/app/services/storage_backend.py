"""Storage backend capability checks for media processing."""
from __future__ import annotations

import os


def storage_backend_name() -> str:
    return (os.getenv("STORAGE_BACKEND") or "local").lower().strip()


def is_local_media_backend() -> bool:
    return storage_backend_name() in ("local", "fs", "filesystem", "")


def require_local_media_processing() -> None:
    """Raise if media workers cannot process objects on this backend."""
    if not is_local_media_backend():
        raise RuntimeError(
            f"Media processing is not available for storage backend "
            f"{storage_backend_name()!r} (DEFERRED — local filesystem required)"
        )
