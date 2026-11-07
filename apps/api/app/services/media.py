"""Media probe, keyframe extraction, storage path resolution, ASR audio extract."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def probe(path: Path | str, *, timeout_s: int = 60) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(str(path))
    if not shutil.which("ffprobe"):
        raise RuntimeError("ffprobe not available")
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
        raise RuntimeError(f"ffprobe failed: {(proc.stderr or '')[:400]}")
    return json.loads(proc.stdout or "{}")


def normalize_probe(raw: dict[str, Any]) -> dict[str, Any]:
    fmt = raw.get("format") or {}
    streams = raw.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)

    duration_ms = None
    try:
        if fmt.get("duration") is not None:
            duration_ms = int(round(float(fmt["duration"]) * 1000))
    except (TypeError, ValueError):
        duration_ms = None

    fps = None
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
        base["width"] = video.get("width")
    if video.get("height"):
        base["height"] = video.get("height")
    return base


def sample_keyframe_timestamps_ms(duration_ms: int, max_frames: int) -> list[int]:
    if max_frames <= 0 or duration_ms <= 0:
        return []
    if max_frames == 1:
        return [max(0, duration_ms // 2)]
    step = duration_ms / max_frames
    return [int(step * i + step / 2) for i in range(max_frames)]


def extract_keyframes(
    path: Path | str,
    out_dir: Path | str,
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


def extract_audio_for_asr(
    path: Path | str,
    out_path: Path | str,
    *,
    timeout_s: int = 300,
    max_duration_s: int | None = None,
) -> Path:
    """Extract mono 16 kHz WAV for ASR via FFmpeg argv (no shell).

    Raises ValueError if no audio stream or FFmpeg fails.
    """
    path = Path(path)
    out_path = Path(out_path)
    if not path.exists():
        raise FileNotFoundError(str(path))
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg not available")
    try:
        raw = probe(path, timeout_s=min(60, timeout_s))
        norm = normalize_probe(raw)
    except Exception as e:
        raise ValueError(f"media probe failed: {type(e).__name__}") from e
    if not norm.get("audio"):
        raise ValueError("asset has no audio stream")
    duration_ms = norm.get("duration_ms")
    if max_duration_s is not None and duration_ms is not None:
        if int(duration_ms) > int(max_duration_s) * 1000:
            raise ValueError(f"media duration exceeds limit ({max_duration_s}s)")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        str(out_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
    if proc.returncode != 0 or not out_path.exists() or out_path.stat().st_size == 0:
        err = (proc.stderr or proc.stdout or "")[:500]
        raise ValueError(f"audio extraction failed: {err or 'empty output'}")
    return out_path


def resolve_storage_path(storage_key: str, storage_root: str | Path | None = None) -> Path:
    """Resolve asset path under storage root; reject path traversal."""
    import os

    root = Path(storage_root or os.getenv("LOCAL_STORAGE_PATH", "./data/storage")).resolve()
    candidate = (root / storage_key.lstrip("/")).resolve()
    if not candidate.is_relative_to(root):
        raise ValueError("path escapes storage root")
    return candidate
