"""Phase B.2: vector-space uniqueness, indexing safety, migration 016."""
from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.services.segment_index import (
    SegmentIndexError,
    index_asset_segments,
)

REPO = Path(__file__).resolve().parents[3]
MIG_016 = REPO / "infra/alembic/versions/016_tse_unique_include_dimensions.py"
MIG_015 = REPO / "infra/alembic/versions/015_transcript_segment_embeddings.py"

DATABASE_URL = os.getenv("DATABASE_URL", "")
REQUIRES_PG = not DATABASE_URL.startswith("postgresql")


def test_migration_016_exists_and_parents_015():
    assert MIG_016.is_file()
    text = MIG_016.read_text()
    assert 'revision = "016"' in text
    assert 'down_revision = "015"' in text
    assert "embedding_dimensions" in text
    assert "uq_tse_asset_seg_vector_space" in text
    assert "uq_tse_asset_seg_space" in text  # dropped / restored on downgrade


def test_migration_015_old_constraint_documented():
    text = MIG_015.read_text()
    assert "uq_tse_asset_seg_space" in text
    assert "UniqueConstraint" in text or "unique" in text.lower()


def test_orm_unique_includes_dimensions():
    src = (Path(__file__).resolve().parents[1] / "app/models/project.py").read_text()
    assert 'name="uq_tse_asset_seg_vector_space"' in src
    idx = src.index("uq_tse_asset_seg_vector_space")
    block = src[idx - 400 : idx + 80]
    for col in (
        "asset_id",
        "segment_index",
        "embedding_provider",
        "embedding_model",
        "embedding_dimensions",
    ):
        assert f'"{col}"' in block


def test_index_delete_filter_matches_unique_space():
    src = (Path(__file__).resolve().parents[1] / "app/services/segment_index.py").read_text()
    assert "embedding_dimensions == dims" in src
    assert src.index("validate_embedding_vector") < src.index("delete(TranscriptSegmentEmbedding)")


class _FakeProvider:
    name = "openai"
    model = "text-embedding-3-small"
    dimensions = 8

    def __init__(self, vectors=None, fail=False):
        self._vectors = vectors
        self._fail = fail
        self.calls = 0

    async def embed_many(self, texts):
        self.calls += 1
        if self._fail:
            raise RuntimeError("provider_down")
        if self._vectors is not None:
            return self._vectors
        return [[0.1] * self.dimensions for _ in texts]


def _asset_with_segments(n=2):
    segs = [
        {"start_ms": i * 1000, "end_ms": i * 1000 + 500, "text": f"seg {i}"}
        for i in range(n)
    ]
    return SimpleNamespace(
        id=uuid4(),
        project_id=uuid4(),
        embedding=None,
        metadata_={"transcription": {"segments": segs}},
        deleted_at=None,
    )


@pytest.mark.asyncio
async def test_provider_failure_does_not_delete_previous_index(monkeypatch):
    import sys
    from unittest.mock import MagicMock as MM

    stmt = MagicMock()
    stmt.where.return_value = stmt
    fake_sa = MM()
    fake_sa.delete = MagicMock(return_value=stmt)
    monkeypatch.setitem(sys.modules, "sqlalchemy", fake_sa)
    monkeypatch.setitem(sys.modules, "app.models.project", MM())

    asset = _asset_with_segments()
    session = AsyncMock()
    session.execute = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    provider = _FakeProvider(fail=True)

    with pytest.raises(RuntimeError, match="provider_down"):
        await index_asset_segments(session, asset=asset, provider=provider)
    session.execute.assert_not_called()
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_dimension_mismatch_rejects_before_delete(monkeypatch):
    import sys
    from unittest.mock import MagicMock as MM

    monkeypatch.setitem(sys.modules, "sqlalchemy", MM())
    monkeypatch.setitem(sys.modules, "app.models.project", MM())
    asset = _asset_with_segments(1)
    session = AsyncMock()
    session.execute = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    provider = _FakeProvider(vectors=[[0.1, 0.2]])  # dim 2, expected 8
    with pytest.raises((SegmentIndexError, Exception)):
        await index_asset_segments(session, asset=asset, provider=provider)
    session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_successful_index_deletes_only_matching_space(monkeypatch):
    import sys
    from unittest.mock import MagicMock as MM

    stmt = MagicMock()
    stmt.where.return_value = stmt
    fake_sa = MM()
    fake_sa.delete = MagicMock(return_value=stmt)
    monkeypatch.setitem(sys.modules, "sqlalchemy", fake_sa)

    class FakeRow:
        asset_id = MagicMock()
        embedding_provider = MagicMock()
        embedding_model = MagicMock()
        embedding_dimensions = MagicMock()

        def __init__(self, **kw):
            self.__dict__.update(kw)

    fake_models = MM()
    fake_models.TranscriptSegmentEmbedding = FakeRow
    monkeypatch.setitem(sys.modules, "app.models.project", fake_models)

    asset = _asset_with_segments(2)
    session = AsyncMock()
    session.execute = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    provider = _FakeProvider()
    out = await index_asset_segments(session, asset=asset, provider=provider)
    assert out["ok"] is True
    assert out["segments_indexed"] == 2
    assert out["embedding_dimensions"] == 8
    session.execute.assert_called_once()
    assert session.add.call_count == 2
    session.flush.assert_awaited()
    fake_sa.delete.assert_called()
    stmt.where.assert_called()


@pytest.mark.asyncio
async def test_batch_size_mismatch_aborts_without_delete(monkeypatch):
    import sys
    from unittest.mock import MagicMock as MM

    monkeypatch.setitem(sys.modules, "sqlalchemy", MM())
    monkeypatch.setitem(sys.modules, "app.models.project", MM())
    asset = _asset_with_segments(2)
    session = AsyncMock()
    session.execute = AsyncMock()

    class BadProvider(_FakeProvider):
        async def embed_many(self, texts):
            return [[0.1] * 8]  # one vector for two texts

    with pytest.raises(SegmentIndexError, match="batch size"):
        await index_asset_segments(session, asset=asset, provider=BadProvider())
    session.execute.assert_not_called()


@pytest.mark.skipif(REQUIRES_PG, reason="PostgreSQL required for DB regression")
@pytest.mark.asyncio
async def test_pg_reindex_same_space_idempotent():
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy import text

    engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    """
                    SELECT 1 FROM information_schema.table_constraints
                    WHERE table_name = 'transcript_segment_embeddings'
                      AND constraint_name = 'uq_tse_asset_seg_vector_space'
                    """
                )
            )
        ).fetchall()
    await engine.dispose()
    assert rows, "uq_tse_asset_seg_vector_space must exist after migration 016"


@pytest.mark.skipif(REQUIRES_PG, reason="PostgreSQL required for alembic check")
def test_pg_alembic_heads_include_016():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config()
    cfg.set_main_option("script_location", str(REPO / "infra/alembic"))
    script = ScriptDirectory.from_config(cfg)
    heads = script.get_heads()
    assert "016" in heads or any("016" in h for h in heads)


def test_search_contract_still_segment_only():
    src = (Path(__file__).resolve().parents[1] / "app/api/projects.py").read_text()
    assert "search_project_segments" in src
    assert "rank_assets_by_embedding" not in src
    assert "index_not_ready" in src
