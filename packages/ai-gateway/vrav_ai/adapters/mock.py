from __future__ import annotations

from typing import AsyncIterator

from vrav_ai.protocol import (
    ChatChunk,
    ChatRequest,
    ChatResponse,
    ProviderCapabilities,
    Usage,
)


class MockAIProvider:
    id = "mock"
    capabilities = ProviderCapabilities(
        streaming=True,
        tools=True,
        structured_output=True,
        vision=False,
    )

    def __init__(self, fixed_reply: str = "Mock reply from VRAV AI Gateway."):
        self.fixed_reply = fixed_reply

    async def chat(self, request: ChatRequest) -> ChatResponse:
        content = self.fixed_reply
        if request.messages:
            last = request.messages[-1].content
            if isinstance(last, str) and last.strip():
                content = f"Echo: {last[:200]}"
        in_tok = sum(len(str(m.content or "")) // 4 for m in request.messages) or 1
        out_tok = len(content) // 4 or 1
        return ChatResponse(
            content=content,
            usage=Usage(input_tokens=in_tok, output_tokens=out_tok, total_tokens=in_tok + out_tok),
            model=request.model,
            raw={"provider": "mock"},
        )

    async def stream_chat(self, request: ChatRequest) -> AsyncIterator[ChatChunk]:
        resp = await self.chat(request)
        text = resp.content or ""
        step = max(1, len(text) // 4)
        for i in range(0, len(text), step):
            yield ChatChunk(delta=text[i : i + step])
        yield ChatChunk(finish_reason="stop", usage=resp.usage)
