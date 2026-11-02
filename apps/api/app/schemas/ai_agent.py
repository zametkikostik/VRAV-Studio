from pydantic import BaseModel, Field


class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=8000)
    top_k: int = Field(default=10, ge=1, le=50)
    model: str = Field(default="mock/default", max_length=128)


class GenerateResponse(BaseModel):
    job_id: str
    status: str
    timeline: dict | None = None
    selected_asset_ids: list[str] = Field(default_factory=list)
    plan_source: str | None = None
