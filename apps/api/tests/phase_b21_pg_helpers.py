"""Shared helpers for Phase B.2.1 PostgreSQL segment tests."""
from __future__ import annotations

import os
import uuid

DATABASE_URL = os.getenv("DATABASE_URL", "")


class DeterministicEmbedder:
    def __init__(self, *, name: str = "mock", model: str = "det-v1", dimensions: int = 8):
        self.name = name
        self.model = model
        self.dimensions = dimensions

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for t in texts:
            h = sum(ord(c) for c in t) % 997
            base = [(h + i) % 13 / 13.0 for i in range(self.dimensions)]
            out.append(base)
        return out


async def engine_session():
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False, autoflush=False)
    return engine, Session


async def seed_project_asset(session, *, segs=None):
    from app.models.user import User
    from app.models.organization import Organization, OrganizationMember
    from app.models.project import Project, Asset
    from app.core.security import hash_password

    uid, oid, pid, aid = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    session.add(
        User(
            id=uid,
            email=f"b21_{uid.hex[:10]}@example.com",
            password_hash=hash_password("TestPass123!"),
            full_name="B21",
            is_active=True,
        )
    )
    await session.flush()
    session.add(Organization(id=oid, name="B21 Org", slug=f"b21-{uid.hex[:8]}", owner_user_id=uid))
    await session.flush()
    session.add(OrganizationMember(organization_id=oid, user_id=uid, role="owner"))
    session.add(
        Project(
            id=pid,
            organization_id=oid,
            name="B21 Project",
            description=None,
            status="draft",
            created_by=uid,
        )
    )
    await session.flush()
    if segs is None:
        segs = [
            {"start_ms": 0, "end_ms": 1000, "text": "alpha clip one"},
            {"start_ms": 1000, "end_ms": 2000, "text": "beta clip two"},
        ]
    session.add(
        Asset(
            id=aid,
            project_id=pid,
            type="video",
            storage_key=f"local/{aid.hex}/clip.mp4",
            filename="clip.mp4",
            mime_type="video/mp4",
            size_bytes=1024,
            metadata_={"transcription": {"segments": segs}},
        )
    )
    await session.flush()
    return uid, oid, pid, aid


async def count_rows(session, asset_id, *, provider=None, model=None, dims=None):
    from sqlalchemy import select, func
    from app.models.project import TranscriptSegmentEmbedding

    q = select(func.count()).select_from(TranscriptSegmentEmbedding).where(
        TranscriptSegmentEmbedding.asset_id == asset_id
    )
    if provider is not None:
        q = q.where(TranscriptSegmentEmbedding.embedding_provider == provider)
    if model is not None:
        q = q.where(TranscriptSegmentEmbedding.embedding_model == model)
    if dims is not None:
        q = q.where(TranscriptSegmentEmbedding.embedding_dimensions == dims)
    return int((await session.execute(q)).scalar_one())


async def texts(session, asset_id, **filters):
    from sqlalchemy import select
    from app.models.project import TranscriptSegmentEmbedding

    q = select(TranscriptSegmentEmbedding.text, TranscriptSegmentEmbedding.segment_index).where(
        TranscriptSegmentEmbedding.asset_id == asset_id
    )
    if filters.get("provider"):
        q = q.where(TranscriptSegmentEmbedding.embedding_provider == filters["provider"])
    if filters.get("model"):
        q = q.where(TranscriptSegmentEmbedding.embedding_model == filters["model"])
    if filters.get("dims") is not None:
        q = q.where(TranscriptSegmentEmbedding.embedding_dimensions == filters["dims"])
    q = q.order_by(TranscriptSegmentEmbedding.segment_index)
    rows = (await session.execute(q)).all()
    return [(r[1], r[0]) for r in rows]
