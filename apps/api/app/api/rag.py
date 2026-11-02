"""RAG semantic search over project assets."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.models.organization import OrganizationMember
from app.models.project import Asset, Project
from app.services.rag_search import RagError, deterministic_embed, search_by_text

router = APIRouter(tags=["rag"])


class RagSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    top_k: int = Field(default=10, ge=1, le=50)
    min_score: float = Field(default=0.0, ge=-1.0, le=1.0)


class RagHitOut(BaseModel):
    asset_id: str
    score: float
    filename: str | None = None
    transcript_snippet: str | None = None
    type: str | None = None


class RagSearchResponse(BaseModel):
    project_id: str
    query: str
    hits: list[RagHitOut]


class EmbedRequest(BaseModel):
    text: str = Field(min_length=1, max_length=8000)


class EmbedResponse(BaseModel):
    dim: int
    embedding: list[float]


async def _get_project_for_user(db: DbSession, user_id: uuid.UUID, project_id: uuid.UUID) -> Project:
    result = await db.execute(
        select(Project)
        .join(OrganizationMember, OrganizationMember.organization_id == Project.organization_id)
        .where(
            Project.id == project_id,
            OrganizationMember.user_id == user_id,
            Project.deleted_at.is_(None),
        )
    )
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


@router.post("/projects/{project_id}/rag/search", response_model=RagSearchResponse)
async def rag_search(project_id: str, body: RagSearchRequest, user: CurrentUser, db: DbSession):
    try:
        pid = uuid.UUID(project_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project_id")
    await _get_project_for_user(db, user.id, pid)

    result = await db.execute(
        select(Asset).where(Asset.project_id == pid, Asset.deleted_at.is_(None))
    )
    rows = result.scalars().all()
    assets = [
        {
            "id": str(a.id),
            "embedding": a.embedding,
            "filename": a.filename,
            "transcript": a.transcript,
            "type": a.type,
        }
        for a in rows
    ]
    try:
        hits = search_by_text(body.query, assets, top_k=body.top_k, min_score=body.min_score)
    except RagError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return RagSearchResponse(
        project_id=project_id,
        query=body.query,
        hits=[
            RagHitOut(
                asset_id=h.asset_id,
                score=h.score,
                filename=h.filename,
                transcript_snippet=h.transcript_snippet,
                type=h.type,
            )
            for h in hits
        ],
    )


@router.post("/rag/embed", response_model=EmbedResponse)
async def rag_embed(body: EmbedRequest, user: CurrentUser):
    """Dev/test embedder. Production should call the configured embedding provider."""
    try:
        emb = deterministic_embed(body.text)
    except RagError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return EmbedResponse(dim=len(emb), embedding=emb)
