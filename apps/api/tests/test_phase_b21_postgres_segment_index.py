"""Phase B.2.1 — PostgreSQL behavioral tests for segment indexing.

Requires DATABASE_URL=postgresql+asyncpg://... (CI e2e job).
No MagicMock for database integrity assertions.
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tests.phase_b21_pg_helpers import (
    DATABASE_URL,
    DeterministicEmbedder,
    count_rows,
    engine_session,
    seed_project_asset,
    texts,
)

REQUIRES_PG = not DATABASE_URL.startswith("postgresql")
pytestmark = pytest.mark.skipif(
    REQUIRES_PG,
    reason="DATABASE_URL must be postgresql+asyncpg://... for segment index PG tests",
)


def test_pg_reindex_same_space_idempotent():
    async def _run():
        from app.services.segment_index import index_asset_segments
        from app.models.project import Asset

        engine, Session = await engine_session()
        try:
            async with Session() as session:
                _, _, _, aid = await seed_project_asset(session)
                await session.commit()
            provider = DeterministicEmbedder(dimensions=8)
            async with Session() as session:
                asset = await session.get(Asset, aid)
                r1 = await index_asset_segments(session, asset=asset, provider=provider)
                await session.commit()
                n1 = await count_rows(session, aid, provider="mock", model="det-v1", dims=8)
            async with Session() as session:
                asset = await session.get(Asset, aid)
                await index_asset_segments(session, asset=asset, provider=provider)
                await session.commit()
                n2 = await count_rows(session, aid, provider="mock", model="det-v1", dims=8)
            assert r1["ok"] is True and n1 == 2 and n2 == 2
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_pg_reindex_after_transcript_change_replaces_text():
    async def _run():
        from app.services.segment_index import index_asset_segments
        from app.models.project import Asset

        engine, Session = await engine_session()
        try:
            provider = DeterministicEmbedder(dimensions=8)
            async with Session() as session:
                _, _, _, aid = await seed_project_asset(session)
                asset = await session.get(Asset, aid)
                await index_asset_segments(session, asset=asset, provider=provider)
                await session.commit()
            async with Session() as session:
                asset = await session.get(Asset, aid)
                asset.metadata_ = {
                    "transcription": {
                        "segments": [
                            {"start_ms": 0, "end_ms": 500, "text": "gamma revised"},
                            {"start_ms": 500, "end_ms": 1500, "text": "delta revised"},
                        ]
                    }
                }
                await index_asset_segments(session, asset=asset, provider=provider)
                await session.commit()
                after = await texts(session, aid, provider="mock", model="det-v1", dims=8)
                assert after[0][1] == "gamma revised"
                assert after[1][1] == "delta revised"
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_pg_distinct_dimensions_are_separate_spaces():
    async def _run():
        from app.services.segment_index import index_asset_segments
        from app.models.project import Asset

        engine, Session = await engine_session()
        try:
            async with Session() as session:
                _, _, _, aid = await seed_project_asset(session)
                await session.commit()
            async with Session() as session:
                asset = await session.get(Asset, aid)
                await index_asset_segments(
                    session, asset=asset, provider=DeterministicEmbedder(model="det-v1", dimensions=8)
                )
                await session.commit()
            async with Session() as session:
                asset = await session.get(Asset, aid)
                await index_asset_segments(
                    session, asset=asset, provider=DeterministicEmbedder(model="det-v1", dimensions=4)
                )
                await session.commit()
                assert await count_rows(session, aid, dims=8) == 2
                assert await count_rows(session, aid, dims=4) == 2
                assert await count_rows(session, aid) == 4
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_pg_distinct_models_are_separate_spaces():
    async def _run():
        from app.services.segment_index import index_asset_segments
        from app.models.project import Asset

        engine, Session = await engine_session()
        try:
            async with Session() as session:
                _, _, _, aid = await seed_project_asset(session)
                await session.commit()
            for model in ("model-a", "model-b"):
                async with Session() as session:
                    asset = await session.get(Asset, aid)
                    await index_asset_segments(
                        session, asset=asset, provider=DeterministicEmbedder(model=model, dimensions=8)
                    )
                    await session.commit()
            async with Session() as session:
                assert await count_rows(session, aid, model="model-a", dims=8) == 2
                assert await count_rows(session, aid, model="model-b", dims=8) == 2
                assert await count_rows(session, aid) == 4
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_pg_reindex_one_space_preserves_other():
    async def _run():
        from app.services.segment_index import index_asset_segments
        from app.models.project import Asset

        engine, Session = await engine_session()
        try:
            async with Session() as session:
                _, _, _, aid = await seed_project_asset(session)
                await session.commit()
            async with Session() as session:
                asset = await session.get(Asset, aid)
                await index_asset_segments(
                    session, asset=asset, provider=DeterministicEmbedder(model="keep", dimensions=8)
                )
                await index_asset_segments(
                    session, asset=asset, provider=DeterministicEmbedder(model="change", dimensions=8)
                )
                await session.commit()
            async with Session() as session:
                asset = await session.get(Asset, aid)
                asset.metadata_ = {
                    "transcription": {
                        "segments": [{"start_ms": 0, "end_ms": 100, "text": "only one now"}]
                    }
                }
                await index_asset_segments(
                    session, asset=asset, provider=DeterministicEmbedder(model="change", dimensions=8)
                )
                await session.commit()
                assert await count_rows(session, aid, model="keep", dims=8) == 2
                assert await count_rows(session, aid, model="change", dims=8) == 1
                assert (await texts(session, aid, model="change", dims=8))[0][1] == "only one now"
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_pg_search_exact_vector_space_only():
    async def _run():
        from app.services.segment_index import index_asset_segments, search_project_segments
        from app.models.project import Asset

        engine, Session = await engine_session()
        try:
            async with Session() as session:
                _, _, pid, aid = await seed_project_asset(session)
                await session.commit()
            p8 = DeterministicEmbedder(model="search-m", dimensions=8)
            p4 = DeterministicEmbedder(model="search-m", dimensions=4)
            async with Session() as session:
                asset = await session.get(Asset, aid)
                await index_asset_segments(session, asset=asset, provider=p8)
                await index_asset_segments(session, asset=asset, provider=p4)
                await session.commit()
            q8 = (await p8.embed_many(["alpha clip one"]))[0]
            async with Session() as session:
                hits = await search_project_segments(
                    session,
                    project_id=pid,
                    query_embedding=q8,
                    provider_name="mock",
                    model="search-m",
                    dimensions=8,
                    top_k=10,
                )
                assert hits
                assert all(h.embedding_model == "search-m" for h in hits)
                assert all(h.asset_id == str(aid) for h in hits)
                assert all(h.snippet and h.start_ms is not None for h in hits)
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_pg_deleted_asset_excluded_from_search():
    async def _run():
        from app.services.segment_index import index_asset_segments, search_project_segments
        from app.models.project import Asset

        engine, Session = await engine_session()
        try:
            provider = DeterministicEmbedder(model="del-m", dimensions=8)
            async with Session() as session:
                _, _, pid, aid = await seed_project_asset(session)
                asset = await session.get(Asset, aid)
                await index_asset_segments(session, asset=asset, provider=provider)
                await session.commit()
            q = (await provider.embed_many(["alpha clip one"]))[0]
            async with Session() as session:
                assert await search_project_segments(
                    session, project_id=pid, query_embedding=q,
                    provider_name="mock", model="del-m", dimensions=8,
                )
            async with Session() as session:
                asset = await session.get(Asset, aid)
                asset.deleted_at = datetime.now(timezone.utc)
                await session.commit()
            async with Session() as session:
                assert await search_project_segments(
                    session, project_id=pid, query_embedding=q,
                    provider_name="mock", model="del-m", dimensions=8,
                ) == []
                assert await count_rows(session, aid) >= 1
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_pg_provider_failure_preserves_previous_index():
    async def _run():
        from app.services.segment_index import index_asset_segments
        from app.models.project import Asset

        engine, Session = await engine_session()
        try:
            ok = DeterministicEmbedder(model="pfail", dimensions=8)

            class Boom(DeterministicEmbedder):
                async def embed_many(self, texts):
                    raise RuntimeError("provider_down")

            async with Session() as session:
                _, _, _, aid = await seed_project_asset(session)
                asset = await session.get(Asset, aid)
                await index_asset_segments(session, asset=asset, provider=ok)
                await session.commit()
                before = await texts(session, aid, model="pfail", dims=8)
            async with Session() as session:
                asset = await session.get(Asset, aid)
                with pytest.raises(RuntimeError, match="provider_down"):
                    await index_asset_segments(
                        session, asset=asset, provider=Boom(model="pfail", dimensions=8)
                    )
                await session.rollback()
            async with Session() as session:
                assert await texts(session, aid, model="pfail", dims=8) == before
                assert await count_rows(session, aid, model="pfail", dims=8) == 2
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_pg_invalid_batch_does_not_delete():
    async def _run():
        from app.services.segment_index import index_asset_segments, SegmentIndexError
        from app.models.project import Asset

        engine, Session = await engine_session()
        try:
            ok = DeterministicEmbedder(model="batch", dimensions=8)

            class BadBatch(DeterministicEmbedder):
                async def embed_many(self, texts):
                    return [[0.1] * self.dimensions]

            async with Session() as session:
                _, _, _, aid = await seed_project_asset(session)
                asset = await session.get(Asset, aid)
                await index_asset_segments(session, asset=asset, provider=ok)
                await session.commit()
            async with Session() as session:
                asset = await session.get(Asset, aid)
                with pytest.raises(SegmentIndexError, match="batch size"):
                    await index_asset_segments(
                        session, asset=asset, provider=BadBatch(model="batch", dimensions=8)
                    )
                await session.rollback()
            async with Session() as session:
                assert await count_rows(session, aid, model="batch", dims=8) == 2
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_pg_session_rollback_restores_index_after_flush():
    async def _run():
        from app.services.segment_index import index_asset_segments
        from app.models.project import Asset

        engine, Session = await engine_session()
        try:
            provider = DeterministicEmbedder(model="tx", dimensions=8)
            async with Session() as session:
                _, _, _, aid = await seed_project_asset(session)
                asset = await session.get(Asset, aid)
                await index_asset_segments(session, asset=asset, provider=provider)
                await session.commit()
                original = await texts(session, aid, model="tx", dims=8)
            async with Session() as session:
                asset = await session.get(Asset, aid)
                asset.metadata_ = {
                    "transcription": {
                        "segments": [{"start_ms": 0, "end_ms": 50, "text": "should not stick"}]
                    }
                }
                await index_asset_segments(session, asset=asset, provider=provider)
                await session.rollback()
            async with Session() as session:
                assert await texts(session, aid, model="tx", dims=8) == original
                assert await count_rows(session, aid, model="tx", dims=8) == 2
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_pg_constraint_016_present():
    async def _run():
        from sqlalchemy import text

        engine, Session = await engine_session()
        try:
            async with engine.connect() as conn:
                names = {
                    r[0]
                    for r in (
                        await conn.execute(
                            text(
                                """
                                SELECT constraint_name
                                FROM information_schema.table_constraints
                                WHERE table_name = 'transcript_segment_embeddings'
                                  AND constraint_type = 'UNIQUE'
                                """
                            )
                        )
                    ).fetchall()
                }
                assert "uq_tse_asset_seg_vector_space" in names
                cols = {
                    r[0]
                    for r in (
                        await conn.execute(
                            text(
                                """
                                SELECT column_name
                                FROM information_schema.constraint_column_usage
                                WHERE constraint_name = 'uq_tse_asset_seg_vector_space'
                                """
                            )
                        )
                    ).fetchall()
                }
                assert cols == {
                    "asset_id",
                    "segment_index",
                    "embedding_provider",
                    "embedding_model",
                    "embedding_dimensions",
                }
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_pg_migration_016_downgrade_aborts_on_multi_dimension_conflict():
    """Alembic env.py uses asyncio.run(); never call command.* inside a running loop."""
    from alembic.config import Config
    from alembic import command
    from sqlalchemy import text
    from app.services.segment_index import index_asset_segments
    from app.models.project import Asset

    async def _seed_conflict():
        engine, Session = await engine_session()
        try:
            async with Session() as session:
                _, _, _, aid = await seed_project_asset(session)
                await session.commit()
            async with Session() as session:
                asset = await session.get(Asset, aid)
                await index_asset_segments(
                    session, asset=asset, provider=DeterministicEmbedder(model="m", dimensions=8)
                )
                await index_asset_segments(
                    session, asset=asset, provider=DeterministicEmbedder(model="m", dimensions=4)
                )
                await session.commit()
                assert await count_rows(session, aid) == 4
            return aid
        finally:
            await engine.dispose()

    aid = asyncio.run(_seed_conflict())

    root = Path(__file__).resolve().parents[1]
    cfg = Config(str(root / "alembic.ini"))
    # env.py reads DATABASE_URL via get_settings(); no nested event loop here
    with pytest.raises(Exception) as ei:
        command.downgrade(cfg, "015")
    msg = str(ei.value).lower()
    assert "cannot downgrade" in msg or "multiple vector" in msg or "conflict" in msg

    async def _verify_preserved():
        engine, Session = await engine_session()
        try:
            async with Session() as session:
                assert await count_rows(session, aid) == 4
            async with engine.connect() as conn:
                ver = (await conn.execute(text("SELECT version_num FROM alembic_version"))).scalar_one()
            assert ver == "016"
        finally:
            await engine.dispose()

    asyncio.run(_verify_preserved())


def test_pg_migration_016_roundtrip_on_compatible_data():
    """Compatible data: 016→015→016 via Alembic; verify state with asyncpg only.

    No synchronous create_engine / psycopg — Alembic env.py already runs migrations
    through asyncpg + asyncio.run (must not nest).
    """
    from alembic.config import Config
    from alembic import command
    from sqlalchemy import text

    root = Path(__file__).resolve().parents[1]
    cfg = Config(str(root / "alembic.ini"))

    uq_sql = """
        SELECT constraint_name FROM information_schema.table_constraints
        WHERE table_name = 'transcript_segment_embeddings'
          AND constraint_type = 'UNIQUE'
    """

    async def _wipe_and_assert_016():
        engine, _ = await engine_session()
        try:
            async with engine.begin() as conn:
                await conn.execute(text("DELETE FROM transcript_segment_embeddings"))
                ver = (await conn.execute(text("SELECT version_num FROM alembic_version"))).scalar_one()
            assert ver == "016"
        finally:
            await engine.dispose()

    async def _assert_revision(expected: str, *, require_uq: str, forbid_uq: str | None = None):
        engine, _ = await engine_session()
        try:
            async with engine.connect() as conn:
                ver = (await conn.execute(text("SELECT version_num FROM alembic_version"))).scalar_one()
                assert ver == expected
                uq = {r[0] for r in (await conn.execute(text(uq_sql))).fetchall()}
                assert require_uq in uq
                if forbid_uq:
                    assert forbid_uq not in uq
        finally:
            await engine.dispose()

    # Start from head with no multi-dimension rows
    command.upgrade(cfg, "head")
    asyncio.run(_wipe_and_assert_016())

    command.downgrade(cfg, "015")
    asyncio.run(
        _assert_revision(
            "015",
            require_uq="uq_tse_asset_seg_space",
            forbid_uq="uq_tse_asset_seg_vector_space",
        )
    )

    command.upgrade(cfg, "016")
    asyncio.run(
        _assert_revision(
            "016",
            require_uq="uq_tse_asset_seg_vector_space",
            forbid_uq="uq_tse_asset_seg_space",
        )
    )
