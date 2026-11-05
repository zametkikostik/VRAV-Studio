"""Transcription foundation via provider interface (no secrets in logs)."""
from __future__ import annotations

from typing import Any, Protocol


class TranscriptionProvider(Protocol):
    async def transcribe(self, *, audio_path: str, language: str | None = None) -> dict[str, Any]:
        """Return {text, segments:[{start_ms,end_ms,text}], provider}."""
        ...


class MockTranscriptionProvider:
    """Deterministic provider for tests/CI — not a live ASR claim."""

    async def transcribe(self, *, audio_path: str, language: str | None = None) -> dict[str, Any]:
        return {
            "text": "mock transcript for testing",
            "segments": [{"start_ms": 0, "end_ms": 1000, "text": "mock transcript for testing"}],
            "provider": "mock",
        }


def get_transcription_provider(name: str | None = None) -> TranscriptionProvider:
    # Live providers (Whisper API, etc.) deferred until credentials exist
    return MockTranscriptionProvider()
