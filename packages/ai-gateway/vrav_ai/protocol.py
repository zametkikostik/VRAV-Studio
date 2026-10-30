from __future__ import annotations

from typing import Any, AsyncIterator, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str
    content: str | list[Any] | None = None
    tool_call_id: str | None = None
    name: str | None = None


class ChatRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    temperature: float | None = None
    max_tokens: int | None = None
    tools: list[dict[str, Any]] | None = None
    response_format: dict[str, Any] | None = None
    stream: bool = False
    extra: dict[str, Any] | None = None


class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost_credits: float | None = None


class ChatChunk(BaseModel):
    delta: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    finish_reason: str | None = None
    usage: Usage | None = None


class ChatResponse(BaseModel):
    content: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    usage: Usage = Field(default_factory=Usage)
    model: str | None = None
    raw: dict[str, Any] | None = None


class ProviderCapabilities(BaseModel):
    streaming: bool = False
    tools: bool = False
    structured_output: bool = False
    vision: bool = False


@runtime_checkable
class AIProvider(Protocol):
    id: str
    capabilities: ProviderCapabilities

    async def chat(self, request: ChatRequest) -> ChatResponse: ...
    async def stream_chat(self, request: ChatRequest) -> AsyncIterator[ChatChunk]: ...
