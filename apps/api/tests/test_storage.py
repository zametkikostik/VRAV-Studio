import tempfile
from pathlib import Path

import pytest

from app.services.storage import LocalStorageProvider


@pytest.mark.asyncio
async def test_local_storage_put_get_delete():
    with tempfile.TemporaryDirectory() as tmp:
        store = LocalStorageProvider(root=tmp)
        key = "org1/proj1/test.bin"
        meta = await store.put(key, b"hello-vrav", content_type="application/octet-stream")
        assert meta.key == key
        assert meta.size == 10
        data = await store.get(key)
        assert data == b"hello-vrav"
        await store.delete(key)
        with pytest.raises(FileNotFoundError):
            await store.get(key)


def test_make_key():
    store = LocalStorageProvider(root="/tmp")
    key = store.make_key("org-uuid", "proj-uuid", "clip.mp4")
    assert key.startswith("org-uuid/proj-uuid/")
    assert key.endswith(".mp4")
