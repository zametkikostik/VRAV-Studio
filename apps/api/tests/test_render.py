"""FFmpeg render service tests — real ffmpeg."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from app.services.media import ffmpeg_available, probe
from app.services.render import RenderClip, RenderRequest, render_timeline


def _make_color_clip(path: Path, color: str, seconds: float = 0.5) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", f"color=c={color}:s=320x240:d={seconds}",
        "-f", "lavfi", "-i", f"sine=f=440:d={seconds}",
        "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    assert path.exists() and path.stat().st_size > 0


@pytest.mark.skipif(not ffmpeg_available(), reason="ffmpeg not installed")
def test_render_two_clips_produces_playable_mp4(tmp_path: Path):
    a, b, out = tmp_path / "a.mp4", tmp_path / "b.mp4", tmp_path / "out.mp4"
    _make_color_clip(a, "red", 0.4)
    _make_color_clip(b, "blue", 0.4)
    result = render_timeline(RenderRequest(
        clips=[RenderClip(path=a, duration_ms=400), RenderClip(path=b, duration_ms=400)],
        output_path=out, width=320, height=240, fps=25,
    ))
    assert result.ok, result.error
    assert result.size_bytes > 0 and out.exists()
    info = probe(out)
    assert float((info.get("format") or {}).get("duration") or 0) > 0.5


@pytest.mark.skipif(not ffmpeg_available(), reason="ffmpeg not installed")
def test_render_missing_source_fails(tmp_path: Path):
    from app.services.render import RenderError
    with pytest.raises(RenderError):
        render_timeline(RenderRequest(
            clips=[RenderClip(path=tmp_path / "missing.mp4")],
            output_path=tmp_path / "out.mp4",
        ))


@pytest.mark.skipif(not ffmpeg_available(), reason="ffmpeg not installed")
def test_render_with_subtitle_burnin(tmp_path: Path):
    from app.services.render import RenderSubtitle
    a, out = tmp_path / "a.mp4", tmp_path / "out.mp4"
    _make_color_clip(a, "green", 1.0)
    result = render_timeline(RenderRequest(
        clips=[RenderClip(path=a, duration_ms=1000)],
        output_path=out, width=320, height=240, fps=25,
        subtitles=[RenderSubtitle(start_ms=100, end_ms=900, text="Hello VRAV")],
    ))
    assert result.ok, result.error
    assert out.exists() and out.stat().st_size > 0
