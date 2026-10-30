from __future__ import annotations

from typing import AsyncIterator

from vrav_ai.protocol import AIProvider, ChatChunk, ChatRequest, ChatResponse
from vrav_ai.registry import ProviderRegistry


class AIRouter:
    def __init__(self, registry: ProviderRegistry) -> None:
        self.registry = registry

    def _provider_for(self, request: ChatRequest) -> AIProvider:
        provider = self.registry.resolve_by_model(request.model)
        if provider is None:
            raise ValueError(f"No provider for model: {request.model}")
        return provider

    async def chat(self, request: ChatRequest) -> ChatResponse:
        provider = self._provider_for(request)
        if request.stream:
            raise ValueError("Use stream_chat for streaming requests")
        if request.tools and not provider.capabilities.tools:
            raise ValueError(f"Provider {provider.id} does not support tools")
        if request.response_format and not provider.capabilities.structured_output:
            raise ValueError(f"Provider {provider.id} does not support structured output")
        return await provider.chat(request)

    async def stream_chat(self, request: ChatRequest) -> AsyncIterator[ChatChunk]:
        provider = self._provider_for(request)
        if not provider.capabilities.streaming:
            raise ValueError(f"Provider {provider.id} does not support streaming")
        async for chunk in provider.stream_chat(request):
            yield chunk
