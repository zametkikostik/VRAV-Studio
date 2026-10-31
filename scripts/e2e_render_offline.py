#!/usr/bin/env python3
"""Offline e2e: generate clips → FFmpeg render → probe. No DB/network."""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from app.services.media import ffmpeg_available, probe
from app.services.render import RenderClip, RenderRequest, RenderSubtitle, render_timeline


def make_clip(path: Path, color: str, sec: float = 0.5) -> None:
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", f"color=c={color}:s=320x240:d={sec}",
        "-f", "lavfi", "-i", f"sine=f=440:d={sec}",
        "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(path),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise SystemExit(f"ffmpeg gen failed: {r.stderr}")


def main() -> int:
    if not ffmpeg_available():
        print("SKIP: ffmpeg not available")
        return 0
    with tempfile.TemporaryDirectory() as tmp:
        td = Path(tmp)
        a, b, out = td / "a.mp4", td / "b.mp4", td / "out.mp4"
        make_clip(a, "red", 0.4)
        make_clip(b, "blue", 0.4)
        result = render_timeline(RenderRequest(
            clips=[RenderClip(path=a, duration_ms=400), RenderClip(path=b, duration_ms=400)],
            output_path=out, width=320, height=240, fps=25,
            subtitles=[RenderSubtitle(start_ms=50, end_ms=700, text="VRAV")],
        ))
        if not result.ok:
            print("FAIL:", result.error)
            return 1
        info = probe(out)
        dur = float((info.get("format") or {}).get("duration") or 0)
        print(f"PASS size={result.size_bytes} duration={dur:.2f}s")
        return 0 if dur > 0.5 and result.size_bytes > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
