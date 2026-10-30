from __future__ import annotations

import os
from typing import Any, AsyncIterator

import httpx

from vrav_ai.protocol import ChatChunk, ChatRequest, ChatResponse, ProviderCapabilities, Usage

XAI_BASE_URL = os.getenv("XAI_BASE_URL", "https://api.x.ai/v1")


class XAIProvider:
    id = "xai"
    capabilities = ProviderCapabilities(
        streaming=True, tools=True, structured_output=False, vision=False
    )

    def __init__(self, api_key: str | None = None, base_url: str = XAI_BASE_URL):
        self.api_key = api_key or os.getenv("XAI_API_KEY", "")
        self.base_url = base_url.rstrip("/")

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise RuntimeError("XAI_API_KEY is not set")
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def _model_name(self, model: str) -> str:
        if model.startswith("xai/"):
            return model[4:]
        return model

    def _build_body(self, request: ChatRequest, stream: bool) -> dict[str, Any]:
        messages = []
        for m in request.messages:
            msg: dict[str, Any] = {"role": m.role}
            if m.content is not None:
                msg["content"] = m.content
            messages.append(msg)
        body: dict[str, Any] = {
            "model": self._model_name(request.model),
            "messages": messages,
            "stream": stream,
        }
        if request.temperature is not None:
            body["temperature"] = request.temperature
        if request.max_tokens is not None:
            body["max_tokens"] = request.max_tokens
        if request.tools:
            body["tools"] = request.tools
        return body

    def _parse_usage(self, data: dict[str, Any]) -> Usage:
        u = data.get("usage") or {}
        return Usage(
            input_tokens=int(u.get("prompt_tokens") or 0),
            output_tokens=int(u.get("completion_tokens") or 0),
            total_tokens=int(u.get("total_tokens") or 0),
        )

    async def chat(self, request: ChatRequest) -> ChatResponse:
        body = self._build_body(request, stream=False)
        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.post(f"{self.base_url}/chat/completions", headers=self._headers(), json=body)
            r.raise_for_status()
            data = r.json()
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        usage = self._parse_usage(data)
        if usage.total_tokens == 0:
            usage.total_tokens = usage.input_tokens + usage.output_tokens
        return ChatResponse(
            content=message.get("content"),
            tool_calls=message.get("tool_calls"),
            usage=usage,
            model=data.get("model") or request.model,
            raw=data,
        )

    async def stream_chat(self, request: ChatRequest) -> AsyncIterator[ChatChunk]:
        import json

        body = self._build_body(request, stream=True)
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream("POST", f"{self.base_url}/chat/completions", headers=self._headers(), json=body) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        yield ChatChunk(finish_reason="stop")
                        break
                    try:
                        data = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    choice = (data.get("choices") or [{}])[0]
                    delta = choice.get("delta") or {}
                    yield ChatChunk(
                        delta=delta.get("content"),
                        tool_calls=delta.get("tool_calls"),
                        finish_reason=choice.get("finish_reason"),
                    )
