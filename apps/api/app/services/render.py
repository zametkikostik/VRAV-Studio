"""Timeline render service using FFmpeg (argument arrays only — no shell)."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class RenderError(Exception):
    pass


@dataclass
class RenderClip:
    path: Path
    start_ms: int = 0
    duration_ms: int | None = None
    source_in_ms: int = 0


@dataclass
class RenderSubtitle:
    start_ms: int
    end_ms: int
    text: str


@dataclass
class RenderRequest:
    clips: list[RenderClip]
    output_path: Path
    width: int = 1280
    height: int = 720
    fps: float = 30.0
    video_codec: str = "libx264"
    audio_codec: str = "aac"
    timeout_sec: int = 600
    subtitles: list[RenderSubtitle] = field(default_factory=list)


@dataclass
class RenderResult:
    ok: bool
    output_path: str
    size_bytes: int = 0
    duration_sec: float | None = None
    ffmpeg_returncode: int | None = None
    probe: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    log_tail: str = ""


def _ffmpeg_bin() -> str:
    bin_ = shutil.which("ffmpeg")
    if not bin_:
        raise RenderError("ffmpeg not found on PATH")
    return bin_


def _run(cmd: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)


def render_timeline(req: RenderRequest) -> RenderResult:
    if not req.clips:
        raise RenderError("no clips to render")
    for c in req.clips:
        if not c.path.exists():
            raise RenderError(f"missing source: {c.path}")

    out = req.output_path
    out.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = _ffmpeg_bin()
    with tempfile.TemporaryDirectory(prefix="vrav_render_") as tmp:
        tmp_path = Path(tmp)
        segment_files: list[Path] = []
        logs: list[str] = []

        for i, clip in enumerate(req.clips):
            seg = tmp_path / f"seg_{i:04d}.mp4"
            cmd: list[str] = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error"]
            if clip.source_in_ms > 0:
                cmd += ["-ss", f"{clip.source_in_ms / 1000.0:.3f}"]
            cmd += ["-i", str(clip.path)]
            if clip.duration_ms is not None and clip.duration_ms > 0:
                cmd += ["-t", f"{clip.duration_ms / 1000.0:.3f}"]
            cmd += [
                "-vf",
                f"scale={req.width}:{req.height}:force_original_aspect_ratio=decrease,"
                f"pad={req.width}:{req.height}:(ow-iw)/2:(oh-ih)/2,fps={req.fps}",
                "-c:v", req.video_codec, "-preset", "veryfast",
                "-c:a", req.audio_codec, "-ar", "48000", "-ac", "2",
                "-movflags", "+faststart", str(seg),
            ]
            proc = _run(cmd, timeout=req.timeout_sec)
            logs.append(proc.stderr[-2000:] if proc.stderr else "")
            if proc.returncode != 0 or not seg.exists() or seg.stat().st_size == 0:
                return RenderResult(ok=False, output_path=str(out), ffmpeg_returncode=proc.returncode,
                                    error=f"segment {i} failed", log_tail="\n".join(logs)[-4000:])
            segment_files.append(seg)

        list_file = tmp_path / "concat.txt"
        list_file.write_text("".join(f"file '{s.resolve()}'\n" for s in segment_files), encoding="utf-8")
        cmd_concat = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
                      "-f", "concat", "-safe", "0", "-i", str(list_file), "-c", "copy", str(out)]
        proc = _run(cmd_concat, timeout=req.timeout_sec)
        logs.append(proc.stderr[-2000:] if proc.stderr else "")
        if proc.returncode != 0 or not out.exists() or out.stat().st_size == 0:
            return RenderResult(ok=False, output_path=str(out), ffmpeg_returncode=proc.returncode,
                                error="concat failed", log_tail="\n".join(logs)[-4000:])

    if req.subtitles:
        burned = out.with_name(out.stem + "_sub" + out.suffix)
        vf_parts: list[str] = []
        for sub in req.subtitles:
            text = sub.text.replace("\\", "\\\\").replace(":", "\\:").replace("'", "").replace("%", "")
            start, end = sub.start_ms / 1000.0, sub.end_ms / 1000.0
            vf_parts.append(
                f"drawtext=text='{text}':fontsize=24:fontcolor=white:borderw=2:"
                f"x=(w-text_w)/2:y=h-80:enable='between(t,{start:.3f},{end:.3f})'"
            )
        if vf_parts:
            cmd_sub = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(out),
                       "-vf", ",".join(vf_parts), "-c:a", "copy", str(burned)]
            proc = _run(cmd_sub, timeout=req.timeout_sec)
            logs.append(proc.stderr[-2000:] if proc.stderr else "")
            if proc.returncode != 0 or not burned.exists() or burned.stat().st_size == 0:
                return RenderResult(ok=False, output_path=str(out), ffmpeg_returncode=proc.returncode,
                                    error="subtitle burn-in failed", log_tail="\n".join(logs)[-4000:])
            burned.replace(out)

    from app.services.media import probe
    try:
        info = probe(out)
    except Exception as e:
        return RenderResult(ok=False, output_path=str(out), size_bytes=out.stat().st_size,
                            error=f"probe failed: {e}", log_tail="\n".join(logs)[-4000:])

    duration = None
    try:
        duration = float((info.get("format") or {}).get("duration") or 0) or None
    except (TypeError, ValueError):
        duration = None

    return RenderResult(ok=True, output_path=str(out), size_bytes=out.stat().st_size,
                        duration_sec=duration, ffmpeg_returncode=0, probe=info,
                        log_tail="\n".join(logs)[-2000:])


def export_path_for_job(storage_root: Path, org_id: str, project_id: str, job_id: str) -> Path:
    return storage_root / org_id / project_id / "exports" / f"{job_id}.mp4"
