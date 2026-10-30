"""FFmpeg helpers. Uses system ffmpeg/ffprobe when available."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def probe(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(str(path))
    if not shutil.which("ffprobe"):
        return {
            "status": "ffprobe_not_installed",
            "path": str(path),
            "size_bytes": path.stat().st_size,
        }
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", "-show_streams", str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or "ffprobe failed")
    return json.loads(proc.stdout)
