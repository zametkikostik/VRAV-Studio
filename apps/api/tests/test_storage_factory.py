import os

from app.services.storage import LocalStorageProvider, get_storage


def test_default_is_local(monkeypatch):
    monkeypatch.delenv("STORAGE_BACKEND", raising=False)
    import app.services.storage as mod

    mod._storage = None
    s = get_storage()
    assert isinstance(s, LocalStorageProvider)


def test_s3_factory_selects_s3_class(monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "minio")
    import app.services.storage as mod

    mod._storage = None
    s = get_storage()
    assert s.__class__.__name__ == "S3StorageProvider"
    mod._storage = None
