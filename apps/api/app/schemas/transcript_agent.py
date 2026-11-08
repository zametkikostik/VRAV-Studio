"""Pydantic schemas for Phase C grounded transcript agent."""
from __future__ import annotations

from pydantic import BaseModel, Field


class AgentQueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=8, ge=1, le=20)
    min_score: float = Field(default=0.0, ge=-1.0, le=1.0)
    generate_answer: bool = True


class AgentMatchOut(BaseModel):
    asset_id: str
    filename: str | None = None
    segment_id: str
    start_ms: int
    end_ms: int
    snippet: str
    score: float
    embedding_model: str | None = None


class AgentQueryResponse(BaseModel):
    query: str
    status: str  # ok | no_relevant_results | index_not_ready | provider_error | retrieval_only
    grounded_answer: str
    matches: list[AgentMatchOut] = Field(default_factory=list)
    embedding_model: str | None = None
    warnings: list[str] = Field(default_factory=list)
    detail: str | None = None
