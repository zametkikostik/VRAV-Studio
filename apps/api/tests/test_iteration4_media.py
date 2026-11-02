"""Iteration 4: FFmpegCompiler video/audio/overlay + path safety."""
from __future__ import annotations

import pytest

from app.services.ffmpeg_compiler import compile_timeline, safe_media_path

PID = "11111111-1111-1111-1111-111111111111"
A1 = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
A2 = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
A3 = "cccccccc-cccc-cccc-cccc-cccccccccccc"


def _paths(**extra):
    base = {
        A1: "/storage/org/a.mp4",
        A2: "/storage/org/b.mp4",
        A3: "/storage/org/voice.wav",
    }
    base.update(extra)
    return base


def test_compile_two_videos_uses_concat_filter():
    tl = {
        "project_id": PID,
        "source_asset_ids": [A1, A2],
        "clips": [
            {"asset_id": A1, "track_type": "video", "duration_ms": 2000, "timeline_start_ms": 0},
            {"asset_id": A2, "track_type": "video", "duration_ms": 1500, "timeline_start_ms": 2000},
        ],
        "output": {"width": 640, "height": 360, "fps": 24},
    }
    compiled = compile_timeline(tl, _paths(), "/tmp/w", "/tmp/out.mp4")
    argv = compiled.all_argv()[0]
    assert "-filter_complex" in argv
    fc = argv[argv.index("-filter_complex") + 1]
    assert "concat=" in fc
    assert "setsar=1" in fc


def test_compile_video_plus_audio_volume_amix():
    tl = {
        "project_id": PID,
        "source_asset_ids": [A1, A3],
        "clips": [
            {"asset_id": A1, "track_type": "video", "duration_ms": 3000, "timeline_start_ms": 0},
            {
                "asset_id": A3,
                "track_type": "audio",
                "duration_ms": 3000,
                "timeline_start_ms": 0,
                "effects": {"volume": 0.5, "afade_in_ms": 200},
            },
        ],
        "output": {"width": 640, "height": 360, "fps": 30},
    }
    compiled = compile_timeline(tl, _paths(), "/tmp/w", "/tmp/out.mp4")
    fc = compiled.all_argv()[0]
    fc = fc[fc.index("-filter_complex") + 1]
    assert "volume=0.5" in fc
    assert "afade=" in fc or "atrim=" in fc


def test_compile_title_overlay_drawtext():
    tl = {
        "project_id": PID,
        "source_asset_ids": [A1, A2],
        "clips": [
            {"asset_id": A1, "track_type": "video", "duration_ms": 2000, "timeline_start_ms": 0},
            {
                "asset_id": A2,
                "track_type": "overlay",
                "duration_ms": 2000,
                "timeline_start_ms": 0,
                "effects": {"text": "Hello Title", "fontsize": 28},
            },
        ],
        "output": {"width": 640, "height": 360, "fps": 30},
    }
    compiled = compile_timeline(tl, _paths(), "/tmp/w", "/tmp/out.mp4")
    fc = compiled.all_argv()[0]
    fc = fc[fc.index("-filter_complex") + 1]
    assert "drawtext=" in fc
    assert "Hello Title" in fc


def test_path_traversal_rejected():
    with pytest.raises(ValueError, match="traversal"):
        safe_media_path("/storage/org/../../etc/passwd")
    tl = {
        "project_id": PID,
        "source_asset_ids": [A1],
        "clips": [
            {"asset_id": A1, "track_type": "video", "duration_ms": 1000, "timeline_start_ms": 0},
        ],
    }
    with pytest.raises(ValueError, match="traversal"):
        compile_timeline(tl, {A1: "/data/../secret.mp4"}, "/tmp/w", "/tmp/o.mp4")


def test_golden_single_video_argv():
    tl = {
        "version": "1.0",
        "project_id": PID,
        "source_asset_ids": [A1],
        "clips": [
            {
                "asset_id": A1,
                "track_type": "video",
                "source_in_ms": 0,
                "duration_ms": 2000,
                "timeline_start_ms": 0,
            }
        ],
        "output": {"width": 640, "height": 360, "fps": 24, "video_codec": "libx264", "audio_codec": "aac"},
    }
    compiled = compile_timeline(tl, {A1: "/storage/org/a.mp4"}, "/tmp/w", "/tmp/out/final.mp4")
    argv = compiled.all_argv()[0]
    assert argv[0] == "ffmpeg"
    assert argv[1:5] == ["-y", "-hide_banner", "-loglevel", "error"]
    assert "-i" in argv
    assert argv[argv.index("-i") + 1] == "/storage/org/a.mp4"
    assert "-t" in argv
    assert argv[argv.index("-t") + 1] == "2.000"
    assert any("scale=640:360" in x for x in argv)
    assert argv[-1] == "/tmp/out/final.mp4"


def test_xfade_when_effect_set():
    tl = {
        "project_id": PID,
        "source_asset_ids": [A1, A2],
        "clips": [
            {"asset_id": A1, "track_type": "video", "duration_ms": 2000, "timeline_start_ms": 0},
            {
                "asset_id": A2,
                "track_type": "video",
                "duration_ms": 2000,
                "timeline_start_ms": 1500,
                "effects": {"xfade_ms": 500},
            },
        ],
        "output": {"width": 640, "height": 360, "fps": 30},
    }
    compiled = compile_timeline(tl, _paths(), "/tmp/w", "/tmp/out.mp4")
    fc = compiled.all_argv()[0]
    fc = fc[fc.index("-filter_complex") + 1]
    assert "xfade=" in fc
