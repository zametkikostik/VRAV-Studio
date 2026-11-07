"""Live ASR provider adapters — mocked HTTP only (no real API keys)."""
from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from app.services.transcription import (
    DeepgramProvider,
    MockTranscriptionProvider,
    OpenAIWhisperProvider,
    TranscriptionAuthError,
    TranscriptionProviderError,
    TranscriptionUnavailableError,
    get_transcription_provider,
    normalize_deepgram_response,
    normalize_openai_verbose_json,
    validate_transcript_payload,
)


def test_normalize_openai_verbose_json():
    raw = {
        "text": "hello world",
        "language": "en",
        "segments": [
            {"start": 0.0, "end": 0.5, "text": " hello"},
            {"start": 0.5, "end": 1.2, "text": " world"},
        ],
    }
    out = normalize_openai_verbose_json(raw, model="whisper-1")
    assert out["provider"] == "openai"
    assert out["text"] == "hello world"
    assert out["segments"][0]["start_ms"] == 0
    assert out["segments"][0]["end_ms"] == 500
    assert out["segments"][1]["start_ms"] == 500
    assert out["segments"][1]["end_ms"] == 1200
    validate_transcript_payload(out)


def test_normalize_openai_text_only_no_fabricated_duration():
    out = normalize_openai_verbose_json({"text": "only text"}, model="whisper-1")
    assert out["segments"] == [{"start_ms": 0, "end_ms": 0, "text": "only text"}]


def test_normalize_deepgram_utterances():
    raw = {
        "results": {
            "channels": [{"alternatives": [{"transcript": "hi there", "words": []}]}],
            "utterances": [
                {"start": 0.1, "end": 0.8, "transcript": "hi"},
                {"start": 0.9, "end": 1.5, "transcript": "there"},
            ],
        },
        "metadata": {"language": "en"},
    }
    out = normalize_deepgram_response(raw, model="nova-2")
    assert out["provider"] == "deepgram"
    assert out["text"] == "hi there"
    assert out["segments"][0]["start_ms"] == 100
    assert out["segments"][1]["end_ms"] == 1500
    validate_transcript_payload(out)


def test_get_provider_mock_explicit(monkeypatch):
    monkeypatch.setenv("TRANSCRIPTION_PROVIDER", "mock")
    p = get_transcription_provider()
    assert isinstance(p, MockTranscriptionProvider)


def test_get_provider_openai_requires_key(monkeypatch):
    monkeypatch.setenv("TRANSCRIPTION_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(TranscriptionUnavailableError, match="OPENAI_API_KEY"):
        get_transcription_provider()


def test_get_provider_deepgram_requires_key(monkeypatch):
    monkeypatch.setenv("TRANSCRIPTION_PROVIDER", "deepgram")
    monkeypatch.delenv("DEEPGRAM_API_KEY", raising=False)
    with pytest.raises(TranscriptionUnavailableError, match="DEEPGRAM_API_KEY"):
        get_transcription_provider()


def test_get_provider_openai_ok(monkeypatch):
    monkeypatch.setenv("TRANSCRIPTION_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-real")
    p = get_transcription_provider()
    assert isinstance(p, OpenAIWhisperProvider)


def test_get_provider_deepgram_ok(monkeypatch):
    monkeypatch.setenv("TRANSCRIPTION_PROVIDER", "deepgram")
    monkeypatch.setenv("DEEPGRAM_API_KEY", "dg-test-not-real")
    p = get_transcription_provider()
    assert isinstance(p, DeepgramProvider)


def test_openai_auth_error_no_retry(tmp_path):
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"RIFF" + b"\x00" * 100)

    class FakeResp:
        status_code = 401

        def json(self):
            return {"error": "nope"}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            return FakeResp()

    prov = OpenAIWhisperProvider(api_key="bad", max_retries=3)
    with patch("app.services.transcription.httpx.AsyncClient", return_value=FakeClient()):
        with pytest.raises(TranscriptionAuthError):
            asyncio.run(prov.transcribe(audio_path=str(audio)))


def test_openai_success_mocked(tmp_path):
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"RIFF" + b"\x00" * 100)

    class FakeResp:
        status_code = 200

        def json(self):
            return {
                "text": "ok",
                "segments": [{"start": 0, "end": 1, "text": "ok"}],
            }

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            return FakeResp()

    prov = OpenAIWhisperProvider(api_key="sk", max_retries=0)
    with patch("app.services.transcription.httpx.AsyncClient", return_value=FakeClient()):
        out = asyncio.run(prov.transcribe(audio_path=str(audio)))
    assert out["text"] == "ok"
    assert out["provider"] == "openai"


def test_deepgram_success_mocked(tmp_path):
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"\x00" * 50)

    class FakeResp:
        status_code = 200

        def json(self):
            return {
                "results": {
                    "channels": [{"alternatives": [{"transcript": "dg ok", "words": []}]}],
                    "utterances": [{"start": 0, "end": 2, "transcript": "dg ok"}],
                }
            }

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            return FakeResp()

    prov = DeepgramProvider(api_key="tok", max_retries=0)
    with patch("app.services.transcription.httpx.AsyncClient", return_value=FakeClient()):
        out = asyncio.run(prov.transcribe(audio_path=str(audio)))
    assert out["text"] == "dg ok"
    assert out["provider"] == "deepgram"


def test_openai_rejects_oversized(tmp_path):
    audio = tmp_path / "big.wav"
    audio.write_bytes(b"x" * 100)
    prov = OpenAIWhisperProvider(api_key="sk", max_upload_bytes=10, max_retries=0)
    with pytest.raises(TranscriptionProviderError, match="upload limit"):
        asyncio.run(prov.transcribe(audio_path=str(audio)))
