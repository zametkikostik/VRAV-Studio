"""Transcription foundation via provider interface (no secrets in logs)."""
from __future__ import annotations

import os
from typing import Any, Protocol


class TranscriptionUnavailableError(Exception):
    """No live transcription provider configured."""


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


def validate_transcript_payload(payload: dict[str, Any]) -> dict[str, Any]:
    text = (payload.get("text") or "").strip()
    if not text:
        raise ValueError("empty transcript")
    segments = payload.get("segments") or []
    if not isinstance(segments, list):
        raise ValueError("segments must be a list")
    clean: list[dict[str, Any]] = []
    for s in segments:
        if not isinstance(s, dict):
            continue
        try:
            start = int(s.get("start_ms", 0))
            end = int(s.get("end_ms", start))
        except (TypeError, ValueError) as e:
            raise ValueError(f"invalid segment timestamps: {e}") from e
        if start < 0 or end < start:
            raise ValueError("segment timestamps out of order")
        st = (s.get("text") or "").strip()
        if not st:
            continue
        clean.append({"start_ms": start, "end_ms": end, "text": st})
    return {
        "text": text,
        "segments": clean,
        "provider": str(payload.get("provider") or "unknown"),
    }


def get_transcription_provider(name: str | None = None) -> TranscriptionProvider:
    """Select provider explicitly.

    Production: set TRANSCRIPTION_PROVIDER=mock only for intentional mock;
    otherwise require a live provider (currently none → unavailable).
    Tests: TRANSCRIPTION_PROVIDER=mock or ENVIRONMENT=test.
    """
    chosen = (name or os.getenv("TRANSCRIPTION_PROVIDER") or "").strip().lower()
    env = (os.getenv("ENVIRONMENT") or os.getenv("APP_ENV") or "development").lower()
    if chosen in ("mock", "test") or env in ("test", "ci"):
        return MockTranscriptionProvider()
    if not chosen or chosen in ("none", "off", "disabled"):
        raise TranscriptionUnavailableError(
            "transcription provider not configured (set TRANSCRIPTION_PROVIDER=mock for tests only)"
        )
    raise TranscriptionUnavailableError(
        f"transcription provider '{chosen}' is not implemented (DEFERRED)"
    )
