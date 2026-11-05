"""Iteration 12: media probe normalization, keyframes limits, plan context enrichment."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.media import merge_probe_metadata, normalize_probe, resolve_storage_path
from app.services.plan_generate import asset_row_to_context, duration_ms_from_asset_row, build_limitations


FFPROBE_VIDEO = {
    "format": {
        "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
        "duration": "12.5",
        "size": "1048576",
        "bit_rate": "800000",
    },
    "streams": [
        {
            "codec_type": "video",
            "codec_name": "h264",
            "width": 1920,
            "height": 1080,
            "avg_frame_rate": "30/1",
            "pix_fmt": "yuv420p",
        },
        {
            "codec_type": "audio",
            "codec_name": "aac",
            "sample_rate": "48000",
            "channels": 2,
        },
    ],
}

FFPROBE_AUDIO = {
    "format": {"format_name": "mp3", "duration": "3.2", "size": "50000"},
    "streams": [
        {
            "codec_type": "audio",
            "codec_name": "mp3",
            "sample_rate": "44100",
            "channels": 1,
        }
    ],
}


def test_normalize_video_probe():
    n = normalize_probe(FFPROBE_VIDEO)
    assert n["status"] == "ok"
    assert n["duration_ms"] == 12500
    assert n["video"]["width"] == 1920
    assert n["video"]["height"] == 1080
    assert n["video"]["fps"] == 30.0
    assert n["video"]["codec"] == "h264"
    assert n["audio"]["codec"] == "aac"
    assert n["audio"]["channels"] == 2


def test_normalize_audio_only():
    n = normalize_probe(FFPROBE_AUDIO)
    assert n["duration_ms"] == 3200
    assert n["video"] is None
    assert n["audio"]["sample_rate"] == 44100


def test_normalize_ffprobe_missing():
    n = normalize_probe({"status": "ffprobe_not_installed", "size_bytes": 10})
    assert n["status"] == "ffprobe_not_installed"


def test_merge_preserves_unrelated_metadata():
    existing = {"custom": "keep", "duration_ms": 1}
    n = normalize_probe(FFPROBE_VIDEO)
    merged = merge_probe_metadata(existing, n)
    assert merged["custom"] == "keep"
    assert merged["duration_ms"] == 12500
    assert merged["probe"]["video"]["width"] == 1920


def test_resolve_storage_rejects_traversal(tmp_path):
    root = tmp_path / "store"
    root.mkdir()
    with pytest.raises(ValueError, match="escapes"):
        resolve_storage_path("../etc/passwd", storage_root=str(root))


def test_asset_context_from_probe_metadata():
    asset = SimpleNamespace(
        id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        type="video",
        filename="a.mp4",
        transcript="hello product demo",
        mime_type="video/mp4",
        metadata_={
            "probe": normalize_probe(FFPROBE_VIDEO),
            "duration_ms": 12500,
            "keyframes": [{"index": 0, "timestamp_ms": 0, "filename": "kf_000.jpg"}],
            "transcription": {
                "status": "completed",
                "segments": [{"start_ms": 0, "end_ms": 500, "text": "hello"}],
            },
        },
    )
    assert duration_ms_from_asset_row(asset) == 12500
    ctx = asset_row_to_context(asset)
    assert ctx["width"] == 1920
    assert ctx["height"] == 1080
    assert ctx["fps"] == 30.0
    assert ctx["transcript_segments"][0]["text"] == "hello"
    assert len(ctx["keyframes"]) == 1


def test_limitations_without_probe():
    lim = build_limitations(
        [{"id": "1", "type": "video", "duration_ms": None, "transcript": None}]
    )
    assert any("duration_unknown" in x for x in lim)
    assert "no_visual_frame_analysis" in lim


def test_malformed_duration_ignored():
    bad = {
        "format": {"duration": "not-a-number"},
        "streams": [{"codec_type": "video", "width": 10, "height": 10, "avg_frame_rate": "0/0"}],
    }
    n = normalize_probe(bad)
    assert n["duration_ms"] is None


def test_mock_transcription_provider():
    import asyncio
    from app.services.transcription import get_transcription_provider

    p = get_transcription_provider()
    out = asyncio.run(p.transcribe(audio_path="/tmp/x.wav"))
    assert out["text"]
    assert out["provider"] == "mock"
    assert out["segments"]
