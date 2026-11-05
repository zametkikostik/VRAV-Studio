"""FFmpeg/FFprobe helpers. Argument arrays only — never shell interpolation."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def probe(path: str | Path, *, timeout_s: int = 60) -> dict[str, Any]:
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
        "ffprobe",
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or "ffprobe failed")
    return json.loads(proc.stdout)


def normalize_probe(raw: dict[str, Any]) -> dict[str, Any]:
    """Map ffprobe JSON to stable technical fields (integer ms, no invention)."""
    if raw.get("status") == "ffprobe_not_installed":
        return {"status": "ffprobe_not_installed", "size_bytes": raw.get("size_bytes")}

    fmt = raw.get("format") or {}
    streams = raw.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)

    duration_ms: int | None = None
    dur = fmt.get("duration")
    if dur is None and video:
        dur = video.get("duration")
    if dur is not None:
        try:
            duration_ms = max(0, int(float(dur) * 1000))
        except (TypeError, ValueError):
            duration_ms = None

    fps: float | None = None
    if video:
        rate = video.get("avg_frame_rate") or video.get("r_frame_rate") or "0/0"
        try:
            if isinstance(rate, str) and "/" in rate:
                num, den = rate.split("/", 1)
                den_f = float(den)
                fps = (float(num) / den_f) if den_f else None
            else:
                fps = float(rate)
        except (TypeError, ValueError, ZeroDivisionError):
            fps = None

    width = int(video["width"]) if video and video.get("width") is not None else None
    height = int(video["height"]) if video and video.get("height") is not None else None

    out: dict[str, Any] = {
        "status": "ok",
        "duration_ms": duration_ms,
        "container": fmt.get("format_name"),
        "size_bytes": int(fmt["size"]) if fmt.get("size") is not None else None,
        "bitrate": int(fmt["bit_rate"]) if fmt.get("bit_rate") is not None else None,
        "video": None,
        "audio": None,
    }
    if video:
        out["video"] = {
            "codec": video.get("codec_name"),
            "width": width,
            "height": height,
            "fps": fps,
            "pix_fmt": video.get("pix_fmt"),
        }
    if audio:
        channels = audio.get("channels")
        try:
            channels_i = int(channels) if channels is not None else None
        except (TypeError, ValueError):
            channels_i = None
        sr = audio.get("sample_rate")
        try:
            sr_i = int(sr) if sr is not None else None
        except (TypeError, ValueError):
            sr_i = None
        out["audio"] = {
            "codec": audio.get("codec_name"),
            "sample_rate": sr_i,
            "channels": channels_i,
        }
    return out


def merge_probe_metadata(existing: dict[str, Any] | None, normalized: dict[str, Any]) -> dict[str, Any]:
    """Idempotent merge: probe fields under metadata['probe']; preserve unrelated keys."""
    base = dict(existing or {})
    base["probe"] = normalized
    if normalized.get("duration_ms") is not None:
        base["duration_ms"] = normalized["duration_ms"]
    video = normalized.get("video") or {}
    if video.get("width"):
        base["width"] = video["width"]
    if video.get("height"):
        base["height"] = video["height"]
    if video.get("fps") is not None:
        base["fps"] = video["fps"]
    return base


def sample_keyframe_timestamps_ms(duration_ms: int, max_frames: int) -> list[int]:
    """Evenly distribute up to max_frames timestamps across [0, duration_ms]."""
    if duration_ms is None or duration_ms <= 0 or max_frames <= 0:
        return []
    n = max(1, min(int(max_frames), 24))
    if n == 1:
        return [max(0, duration_ms // 2)]
    return [int(duration_ms * (i + 1) / (n + 1)) for i in range(n)]


def extract_keyframes(
    path: str | Path,
    out_dir: str | Path,
    *,
    max_frames: int = 8,
    timeout_s: int = 120,
    duration_ms: int | None = None,
) -> list[dict[str, Any]]:
    """Extract up to max_frames JPEGs at representative timestamps (argv only)."""
    path = Path(path)
    out_dir = Path(out_dir)
    if not path.exists():
        raise FileNotFoundError(str(path))
    if not shutil.which("ffmpeg"):
        return []

    dur = duration_ms
    if dur is None:
        try:
            raw = probe(path, timeout_s=min(30, timeout_s))
            norm = normalize_probe(raw)
            dur = norm.get("duration_ms")
        except Exception:
            dur = None
    if not dur or dur <= 0:
        dur = 1000

    timestamps = sample_keyframe_timestamps_ms(int(dur), max_frames)
    if not timestamps:
        return []

    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("kf_*.jpg"):
        try:
            old.unlink()
        except OSError:
            pass

    frames: list[dict[str, Any]] = []
    per_timeout = max(5, timeout_s // max(len(timestamps), 1))
    for i, ts_ms in enumerate(timestamps):
        out_file = out_dir / f"kf_{i:03d}.jpg"
        cmd = [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            f"{ts_ms / 1000.0:.3f}",
            "-i",
            str(path),
            "-frames:v",
            "1",
            "-vf",
            "scale=320:-1",
            "-q:v",
            "5",
            str(out_file),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=per_timeout)
        if proc.returncode != 0 or not out_file.exists() or out_file.stat().st_size == 0:
            continue
        frames.append(
            {
                "index": i,
                "timestamp_ms": int(ts_ms),
                "filename": out_file.name,
                "path": str(out_file),
            }
        )
    return frames


def resolve_storage_path(storage_key: str, storage_root: str | Path | None = None) -> Path:
    """Resolve asset path under storage root; reject path traversal."""
    import os

    root = Path(storage_root or os.getenv("LOCAL_STORAGE_PATH", "./data/storage")).resolve()
    candidate = (root / storage_key.lstrip("/")).resolve()
    if not candidate.is_relative_to(root):
        raise ValueError("path escapes storage root")
    return candidate
