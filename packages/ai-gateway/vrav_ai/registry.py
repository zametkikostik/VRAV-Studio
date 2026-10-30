from __future__ import annotations

from vrav_ai.protocol import AIProvider


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, AIProvider] = {}

    def register(self, provider: AIProvider) -> None:
        self._providers[provider.id] = provider

    def get(self, provider_id: str) -> AIProvider | None:
        return self._providers.get(provider_id)

    def list_ids(self) -> list[str]:
        return list(self._providers.keys())

    def resolve_by_model(self, model: str) -> AIProvider | None:
        if "/" in model:
            provider_id = model.split("/", 1)[0]
            return self.get(provider_id)
        if self._providers:
            return next(iter(self._providers.values()))
        return None
