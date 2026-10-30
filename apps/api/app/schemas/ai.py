from pydantic import BaseModel, Field


class ChatMessageIn(BaseModel):
    role: str
    content: str | None = None


class ChatRequestIn(BaseModel):
    model: str = Field(default="mock/default")
    messages: list[ChatMessageIn]
    temperature: float | None = None
    max_tokens: int | None = None
    organization_id: str


class UsageOut(BaseModel):
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_credits: float | None = None


class ChatResponseOut(BaseModel):
    content: str | None
    model: str | None
    usage: UsageOut
    provider: str | None = None
