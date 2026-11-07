"""Transcription providers: mock (CI) + OpenAI Whisper + Deepgram.

Secrets stay server-side. Never log API keys or Authorization headers.
"""
from __future__ import annotations

import asyncio
import logging
import os
import random
import tempfile
from pathlib import Path
from typing import Any, Protocol

import httpx

logger = logging.getLogger(__name__)


class TranscriptionUnavailableError(Exception):
    """No live transcription provider configured."""


class TranscriptionProviderError(Exception):
    """Provider request failed (non-auth validation or upstream)."""


class TranscriptionAuthError(TranscriptionProviderError):
    """Permanent authentication/authorization failure — do not retry."""


class TranscriptionProvider(Protocol):
    async def transcribe(self, *, audio_path: str, language: str | None = None) -> dict[str, Any]:
        """Return {text, segments:[{start_ms,end_ms,text}], provider, model?, language?}."""
        ...


class MockTranscriptionProvider:
    """Deterministic provider for tests/CI — not a live ASR claim."""

    async def transcribe(self, *, audio_path: str, language: str | None = None) -> dict[str, Any]:
        return {
            "text": "mock transcript for testing",
            "segments": [{"start_ms": 0, "end_ms": 1000, "text": "mock transcript for testing"}],
            "provider": "mock",
            "model": "mock",
            "language": language or "und",
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
    out = {
        "text": text,
        "segments": clean,
        "provider": str(payload.get("provider") or "unknown"),
    }
    if payload.get("model"):
        out["model"] = str(payload["model"])
    if payload.get("language"):
        out["language"] = str(payload["language"])
    return out


def _sec_to_ms(value: Any) -> int:
    try:
        return max(0, int(round(float(value) * 1000)))
    except (TypeError, ValueError):
        return 0


def normalize_openai_verbose_json(data: dict[str, Any], *, model: str) -> dict[str, Any]:
    """Map OpenAI verbose_json transcription response to internal payload."""
    text = (data.get("text") or "").strip()
    segments_out: list[dict[str, Any]] = []
    for s in data.get("segments") or []:
        if not isinstance(s, dict):
            continue
        seg_text = (s.get("text") or "").strip()
        if not seg_text:
            continue
        start_ms = _sec_to_ms(s.get("start", 0))
        end_ms = _sec_to_ms(s.get("end", s.get("start", 0)))
        if end_ms < start_ms:
            end_ms = start_ms
        segments_out.append({"start_ms": start_ms, "end_ms": end_ms, "text": seg_text})
    if not segments_out and text:
        segments_out = [{"start_ms": 0, "end_ms": 0, "text": text}]
    return {
        "text": text,
        "segments": segments_out,
        "provider": "openai",
        "model": model,
        "language": data.get("language"),
    }


def normalize_deepgram_response(data: dict[str, Any], *, model: str) -> dict[str, Any]:
    """Map Deepgram listen response to internal payload."""
    results = data.get("results") or {}
    channels = results.get("channels") or []
    alt = {}
    if channels and isinstance(channels[0], dict):
        alts = channels[0].get("alternatives") or []
        if alts and isinstance(alts[0], dict):
            alt = alts[0]
    text = (alt.get("transcript") or "").strip()
    segments_out: list[dict[str, Any]] = []
    for u in results.get("utterances") or []:
        if not isinstance(u, dict):
            continue
        ut = (u.get("transcript") or "").strip()
        if not ut:
            continue
        start_ms = _sec_to_ms(u.get("start", 0))
        end_ms = _sec_to_ms(u.get("end", u.get("start", 0)))
        if end_ms < start_ms:
            end_ms = start_ms
        segments_out.append({"start_ms": start_ms, "end_ms": end_ms, "text": ut})
    if not segments_out:
        for w in alt.get("words") or []:
            if not isinstance(w, dict):
                continue
            wt = (w.get("word") or w.get("punctuated_word") or "").strip()
            if not wt:
                continue
            start_ms = _sec_to_ms(w.get("start", 0))
            end_ms = _sec_to_ms(w.get("end", w.get("start", 0)))
            segments_out.append({"start_ms": start_ms, "end_ms": end_ms, "text": wt})
    if not segments_out and text:
        segments_out = [{"start_ms": 0, "end_ms": 0, "text": text}]
    return {
        "text": text,
        "segments": segments_out,
        "provider": "deepgram",
        "model": model,
        "language": (data.get("metadata") or {}).get("language") if isinstance(data.get("metadata"), dict) else None,
    }


def _retry_delays(max_retries: int) -> list[float]:
    delays: list[float] = []
    base = 0.5
    for i in range(max(0, max_retries)):
        delays.append(base * (2**i) + random.uniform(0, 0.25))
    return delays


class OpenAIWhisperProvider:
    """OpenAI Audio Transcriptions API (whisper-1)."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str | None = None,
        timeout_s: float = 120.0,
        max_retries: int = 2,
        max_upload_bytes: int = 24 * 1024 * 1024,
    ) -> None:
        self.api_key = api_key
        self.model = model or os.getenv("OPENAI_TRANSCRIPTION_MODEL", "whisper-1")
        self.timeout_s = timeout_s
        self.max_retries = max_retries
        self.max_upload_bytes = max_upload_bytes
        self.base_url = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1").rstrip("/")

    async def transcribe(self, *, audio_path: str, language: str | None = None) -> dict[str, Any]:
        path = Path(audio_path)
        if not path.is_file():
            raise TranscriptionProviderError("audio file not found")
        size = path.stat().st_size
        if size > self.max_upload_bytes:
            raise TranscriptionProviderError(
                f"audio exceeds OpenAI upload limit ({self.max_upload_bytes} bytes)"
            )
        if size == 0:
            raise TranscriptionProviderError("empty audio file")

        url = f"{self.base_url}/audio/transcriptions"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        data: dict[str, str] = {
            "model": self.model,
            "response_format": "verbose_json",
        }
        if language:
            data["language"] = language

        last_err: Exception | None = None
        for attempt, delay in enumerate([0.0] + _retry_delays(self.max_retries)):
            if delay:
                await asyncio.sleep(delay)
            try:
                async with httpx.AsyncClient(timeout=self.timeout_s) as client:
                    with path.open("rb") as fh:
                        files = {"file": (path.name, fh, "application/octet-stream")}
                        resp = await client.post(url, headers=headers, data=data, files=files)
                if resp.status_code in (401, 403):
                    raise TranscriptionAuthError("OpenAI authentication failed")
                if resp.status_code == 429 or resp.status_code >= 500:
                    last_err = TranscriptionProviderError(f"OpenAI transient HTTP {resp.status_code}")
                    continue
                if resp.status_code >= 400:
                    raise TranscriptionProviderError(f"OpenAI HTTP {resp.status_code}")
                payload = resp.json()
                if not isinstance(payload, dict):
                    raise TranscriptionProviderError("OpenAI invalid JSON body")
                return normalize_openai_verbose_json(payload, model=self.model)
            except (TranscriptionAuthError, TranscriptionProviderError):
                raise
            except Exception as e:
                last_err = e
                logger.warning("openai whisper attempt %s failed: %s", attempt, type(e).__name__)
        raise TranscriptionProviderError(f"OpenAI transcription failed: {type(last_err).__name__}")


class DeepgramProvider:
    """Deepgram Listen API."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str | None = None,
        timeout_s: float = 120.0,
        max_retries: int = 2,
        max_upload_bytes: int = 100 * 1024 * 1024,
    ) -> None:
        self.api_key = api_key
        self.model = model or os.getenv("DEEPGRAM_MODEL", "nova-2")
        self.timeout_s = timeout_s
        self.max_retries = max_retries
        self.max_upload_bytes = max_upload_bytes
        self.base_url = os.getenv("DEEPGRAM_API_BASE", "https://api.deepgram.com/v1").rstrip("/")

    async def transcribe(self, *, audio_path: str, language: str | None = None) -> dict[str, Any]:
        path = Path(audio_path)
        if not path.is_file():
            raise TranscriptionProviderError("audio file not found")
        size = path.stat().st_size
        if size > self.max_upload_bytes:
            raise TranscriptionProviderError(
                f"audio exceeds Deepgram upload limit ({self.max_upload_bytes} bytes)"
            )
        if size == 0:
            raise TranscriptionProviderError("empty audio file")

        params: dict[str, str] = {
            "model": self.model,
            "smart_format": "true",
            "utterances": "true",
        }
        if language:
            params["language"] = language
        url = f"{self.base_url}/listen"
        headers = {
            "Authorization": f"Token {self.api_key}",
            "Content-Type": "application/octet-stream",
        }

        last_err: Exception | None = None
        for attempt, delay in enumerate([0.0] + _retry_delays(self.max_retries)):
            if delay:
                await asyncio.sleep(delay)
            try:
                async with httpx.AsyncClient(timeout=self.timeout_s) as client:
                    content = path.read_bytes()
                    resp = await client.post(url, headers=headers, params=params, content=content)
                if resp.status_code in (401, 403):
                    raise TranscriptionAuthError("Deepgram authentication failed")
                if resp.status_code == 429 or resp.status_code >= 500:
                    last_err = TranscriptionProviderError(f"Deepgram transient HTTP {resp.status_code}")
                    continue
                if resp.status_code >= 400:
                    raise TranscriptionProviderError(f"Deepgram HTTP {resp.status_code}")
                payload = resp.json()
                if not isinstance(payload, dict):
                    raise TranscriptionProviderError("Deepgram invalid JSON body")
                return normalize_deepgram_response(payload, model=self.model)
            except (TranscriptionAuthError, TranscriptionProviderError):
                raise
            except Exception as e:
                last_err = e
                logger.warning("deepgram attempt %s failed: %s", attempt, type(e).__name__)
        raise TranscriptionProviderError(f"Deepgram transcription failed: {type(last_err).__name__}")


def get_transcription_provider(name: str | None = None) -> TranscriptionProvider:
    """Select provider explicitly.

    TRANSCRIPTION_PROVIDER=mock|openai|whisper|deepgram
    OPENAI_API_KEY / DEEPGRAM_API_KEY required for live providers.
    Tests: TRANSCRIPTION_PROVIDER=mock or ENVIRONMENT=test.
    """
    chosen = (name or os.getenv("TRANSCRIPTION_PROVIDER") or "").strip().lower()
    env = (os.getenv("ENVIRONMENT") or os.getenv("APP_ENV") or "development").lower()
    if chosen in ("mock", "test") or (not chosen and env in ("test", "ci")):
        return MockTranscriptionProvider()
    if not chosen or chosen in ("none", "off", "disabled"):
        raise TranscriptionUnavailableError(
            "transcription provider not configured (set TRANSCRIPTION_PROVIDER=openai|deepgram|mock)"
        )

    timeout_s = float(os.getenv("ASR_TIMEOUT_SECONDS") or os.getenv("TRANSCRIPTION_TIMEOUT_SECONDS") or "120")
    max_retries = int(os.getenv("ASR_MAX_RETRIES") or os.getenv("TRANSCRIPTION_MAX_RETRIES") or "2")

    if chosen in ("openai", "whisper", "openai_whisper"):
        key = (os.getenv("OPENAI_API_KEY") or "").strip()
        if not key:
            raise TranscriptionUnavailableError("OPENAI_API_KEY is required for openai provider")
        return OpenAIWhisperProvider(api_key=key, timeout_s=timeout_s, max_retries=max_retries)

    if chosen in ("deepgram", "dg"):
        key = (os.getenv("DEEPGRAM_API_KEY") or "").strip()
        if not key:
            raise TranscriptionUnavailableError("DEEPGRAM_API_KEY is required for deepgram provider")
        return DeepgramProvider(api_key=key, timeout_s=timeout_s, max_retries=max_retries)

    raise TranscriptionUnavailableError(
        f"transcription provider '{chosen}' is not supported (use openai|deepgram|mock)"
    )


async def transcribe_media_file(
    media_path: str | Path,
    *,
    provider: TranscriptionProvider | None = None,
    language: str | None = None,
    max_duration_s: int | None = None,
) -> dict[str, Any]:
    """Extract audio if needed, call provider, validate payload. Cleans temp files."""
    from app.services.media import extract_audio_for_asr

    path = Path(media_path)
    provider = provider or get_transcription_provider()
    if max_duration_s is None:
        raw = os.getenv("ASR_MAX_AUDIO_DURATION_SECONDS") or os.getenv("TRANSCRIPTION_MAX_DURATION_SECONDS")
        max_duration_s = int(raw) if raw else None

    tmp_dir = tempfile.mkdtemp(prefix="vrav_asr_")
    audio_path = Path(tmp_dir) / "audio.wav"
    try:
        extract_audio_for_asr(path, audio_path, max_duration_s=max_duration_s)
        result = await provider.transcribe(audio_path=str(audio_path), language=language)
        return validate_transcript_payload(result)
    finally:
        try:
            if audio_path.exists():
                audio_path.unlink()
        except OSError:
            pass
        try:
            Path(tmp_dir).rmdir()
        except OSError:
            pass
