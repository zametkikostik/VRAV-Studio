"""Compile TimelineDefinition into FFmpeg argument vectors (no shell).

Builds argv lists for an external executor (render.py / Celery).
Never uses os.system or subprocess with shell=True.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.services.timeline_definition import TimelineDefinition, validate_timeline


class CompileError(Exception):
    pass


@dataclass
class CompiledSegment:
    index: int
    argv: list[str]
    output: Path


@dataclass
class CompiledTimeline:
    segments: list[CompiledSegment]
    concat_argv: list[str] | None
    final_output: Path
    width: int
    height: int
    fps: float
    notes: list[str] = field(default_factory=list)
    master_argv: list[str] | None = None

    def all_argv(self) -> list[list[str]]:
        if self.master_argv:
            return [self.master_argv]
        cmds = [s.argv for s in self.segments]
        if self.concat_argv:
            cmds.append(self.concat_argv)
        return cmds


def safe_media_path(path: str | Path, *, allow_nonexistent: bool = True) -> Path:
    """Resolve path and reject traversal / empty segments."""
    raw = str(path)
    if not raw or raw.strip() != raw:
        raise ValueError("invalid media path")
    parts = Path(raw).parts
    if ".." in parts:
        raise ValueError("path traversal rejected")
    if re.search(r"(^|/|\\)\.\.(/|\\|$)", raw):
        raise ValueError("path traversal rejected")
    if "\x00" in raw:
        raise ValueError("invalid media path")
    p = Path(raw)
    try:
        resolved = p if allow_nonexistent else p.resolve(strict=True)
    except OSError as e:
        raise ValueError(f"invalid media path: {e}") from e
    if ".." in Path(resolved).parts:
        raise ValueError("path traversal rejected")
    return Path(resolved) if not allow_nonexistent else p


def _esc_drawtext(text: str) -> str:
    t = text.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    t = t.replace("%", "\\%").replace("\n", " ")
    return t[:500]


def _ms(sec_key: float | int) -> str:
    return f"{float(sec_key) / 1000.0:.3f}"


class FFmpegCompilerWorker:
    """Turn a validated TimelineDefinition + asset path map into FFmpeg argv lists."""

    def __init__(self, ffmpeg_bin: str = "ffmpeg"):
        self.ffmpeg_bin = ffmpeg_bin

    def compile(
        self,
        timeline: TimelineDefinition | dict[str, Any],
        asset_paths: dict[str, str | Path],
        work_dir: str | Path,
        final_output: str | Path,
    ) -> CompiledTimeline:
        tl = validate_timeline(timeline)
        work = Path(work_dir)
        work.mkdir(parents=True, exist_ok=True)
        out = Path(final_output)
        out.parent.mkdir(parents=True, exist_ok=True)

        w = tl.output.width
        h = tl.output.height
        fps = float(tl.output.fps)
        vcodec = tl.output.video_codec or "libx264"
        acodec = tl.output.audio_codec or "aac"

        resolved: dict[str, Path] = {}
        for c in tl.clips:
            aid = c.asset_id
            if aid not in asset_paths:
                raise CompileError(f"missing asset path for asset_id={aid}")
            try:
                resolved[aid] = safe_media_path(asset_paths[aid])
            except ValueError as e:
                raise ValueError(str(e)) from e

        videos = sorted(
            [c for c in tl.clips if c.track_type == "video"],
            key=lambda c: (c.timeline_start_ms, c.asset_id),
        )
        audios = sorted(
            [c for c in tl.clips if c.track_type == "audio"],
            key=lambda c: (c.timeline_start_ms, c.asset_id),
        )
        overlays = sorted(
            [c for c in tl.clips if c.track_type == "overlay"],
            key=lambda c: (c.timeline_start_ms, c.asset_id),
        )

        if not videos and not audios:
            raise CompileError("timeline has no video or audio clips")

        notes: list[str] = []
        video_dur = sum(c.duration_ms for c in videos) if videos else 0
        audio_dur = sum(c.duration_ms for c in audios) if audios else 0
        if videos and audios and audio_dur > video_dur + 50:
            notes.append(
                f"audio total {audio_dur}ms exceeds video {video_dur}ms; consider trim"
            )

        use_graph = len(videos) >= 2 or audios or overlays or tl.subtitles
        if use_graph:
            master = self._build_filter_complex_argv(
                tl, videos, audios, overlays, resolved, out, w, h, fps, vcodec, acodec
            )
            return CompiledTimeline(
                segments=[],
                concat_argv=None,
                final_output=out,
                width=w,
                height=h,
                fps=fps,
                notes=notes,
                master_argv=master,
            )

        assert len(videos) == 1
        c = videos[0]
        src = resolved[c.asset_id]
        argv: list[str] = [
            self.ffmpeg_bin,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
        ]
        if c.source_in_ms > 0:
            argv += ["-ss", _ms(c.source_in_ms)]
        argv += ["-i", str(src)]
        if c.duration_ms > 0:
            argv += ["-t", _ms(c.duration_ms)]
        vf = (
            f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}"
        )
        argv += [
            "-vf",
            vf,
            "-r",
            str(fps),
            "-c:v",
            vcodec,
            "-c:a",
            acodec,
            "-movflags",
            "+faststart",
            str(out),
        ]
        seg = CompiledSegment(index=0, argv=argv, output=out)
        return CompiledTimeline(
            segments=[seg],
            concat_argv=None,
            final_output=out,
            width=w,
            height=h,
            fps=fps,
            notes=notes,
            master_argv=argv,
        )

    def _build_filter_complex_argv(
        self,
        tl: TimelineDefinition,
        videos: list,
        audios: list,
        overlays: list,
        resolved: dict[str, Path],
        out: Path,
        w: int,
        h: int,
        fps: float,
        vcodec: str,
        acodec: str,
    ) -> list[str]:
        inputs: list[Path] = []
        input_index: dict[tuple[str, int], int] = {}

        def add_input(clip) -> int:
            key = (clip.asset_id, id(clip))
            if key in input_index:
                return input_index[key]
            idx = len(inputs)
            inputs.append(resolved[clip.asset_id])
            input_index[key] = idx
            return idx

        for c in videos + audios + overlays:
            add_input(c)

        filter_parts: list[str] = []
        vlabels: list[str] = []

        for i, c in enumerate(videos):
            idx = add_input(c)
            start = c.source_in_ms / 1000.0
            dur = c.duration_ms / 1000.0
            end = start + dur
            lab_in = f"vraw{i}"
            filter_parts.append(
                f"[{idx}:v]trim=start={start:.3f}:end={end:.3f},setpts=PTS-STARTPTS,"
                f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
                f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}[{lab_in}]"
            )
            vlabels.append(lab_in)

        vout = "vout"
        if len(vlabels) == 0:
            total_a = max((c.duration_ms for c in audios), default=1000) / 1000.0
            filter_parts.append(
                f"color=c=black:s={w}x{h}:d={total_a:.3f}:r={fps}[{vout}]"
            )
        elif len(vlabels) == 1:
            filter_parts.append(f"[{vlabels[0]}]null[{vout}]")
        else:
            xfade_ms = None
            for c in videos[1:]:
                eff = getattr(c, "effects", None) or {}
                if eff.get("xfade_ms"):
                    xfade_ms = int(eff["xfade_ms"])
                    break
            if xfade_ms and xfade_ms > 0 and len(vlabels) == 2:
                offset = max(videos[0].duration_ms - xfade_ms, 0) / 1000.0
                filter_parts.append(
                    f"[{vlabels[0]}][{vlabels[1]}]xfade=transition=fade:duration={xfade_ms/1000.0:.3f}:offset={offset:.3f}[{vout}]"
                )
            else:
                n = len(vlabels)
                ins = "".join(f"[{lab}]" for lab in vlabels)
                filter_parts.append(f"{ins}concat=n={n}:v=1:a=0[{vout}]")

        current_v = vout
        oi = 0
        for c in overlays:
            idx = add_input(c)
            eff = getattr(c, "effects", None) or {}
            text = eff.get("text") or ""
            if text:
                lab = f"vov{oi}"
                esc = _esc_drawtext(str(text))
                x = int(eff.get("x", 20))
                y = int(eff.get("y", 20))
                fs = int(eff.get("fontsize", 24))
                filter_parts.append(
                    f"[{current_v}]drawtext=text='{esc}':x={x}:y={y}:fontsize={fs}:fontcolor=white[{lab}]"
                )
                current_v = lab
                oi += 1
            else:
                lab = f"vimg{oi}"
                filter_parts.append(
                    f"[{idx}:v]scale={w}:{h}[ov{oi}];[{current_v}][ov{oi}]overlay=0:0[{lab}]"
                )
                current_v = lab
                oi += 1

        for si, sub in enumerate(tl.subtitles or []):
            lab = f"vsub{si}"
            esc = _esc_drawtext(sub.text)
            enable = f"between(t\\,{sub.start_ms/1000.0:.3f}\\,{sub.end_ms/1000.0:.3f})"
            filter_parts.append(
                f"[{current_v}]drawtext=text='{esc}':x=20:y=H-th-40:fontsize=22:"
                f"fontcolor=white:enable='{enable}'[{lab}]"
            )
            current_v = lab

        alabels: list[str] = []
        for i, c in enumerate(audios):
            idx = add_input(c)
            start = c.source_in_ms / 1000.0
            dur = c.duration_ms / 1000.0
            end = start + dur
            eff = getattr(c, "effects", None) or {}
            chain = f"[{idx}:a]atrim=start={start:.3f}:end={end:.3f},asetpts=PTS-STARTPTS"
            vol = eff.get("volume")
            if vol is not None:
                chain += f",volume={float(vol)}"
            if eff.get("loudnorm"):
                chain += ",loudnorm"
            af_in = eff.get("afade_in_ms")
            if af_in:
                chain += f",afade=t=in:st=0:d={float(af_in)/1000.0:.3f}"
            af_out = eff.get("afade_out_ms")
            if af_out:
                st = max(dur - float(af_out) / 1000.0, 0)
                chain += f",afade=t=out:st={st:.3f}:d={float(af_out)/1000.0:.3f}"
            lab = f"a{i}"
            chain += f"[{lab}]"
            filter_parts.append(chain)
            alabels.append(lab)

        aout = None
        if len(alabels) == 1:
            aout = alabels[0]
        elif len(alabels) > 1:
            ins = "".join(f"[{lab}]" for lab in alabels)
            aout = "aout"
            filter_parts.append(f"{ins}amix=inputs={len(alabels)}:duration=longest[{aout}]")

        fc = ";".join(filter_parts)

        argv: list[str] = [
            self.ffmpeg_bin,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
        ]
        for p in inputs:
            argv += ["-i", str(p)]
        argv += ["-filter_complex", fc]
        argv += ["-map", f"[{current_v}]"]
        if aout:
            argv += ["-map", f"[{aout}]"]
        if videos:
            total_ms = sum(c.duration_ms for c in videos)
            argv += ["-t", _ms(total_ms)]
        argv += [
            "-c:v",
            vcodec,
            "-c:a",
            acodec,
            "-movflags",
            "+faststart",
            str(out),
        ]
        return argv


def compile_timeline(
    timeline: TimelineDefinition | dict[str, Any],
    asset_paths: dict[str, str | Path],
    work_dir: str | Path,
    final_output: str | Path,
) -> CompiledTimeline:
    return FFmpegCompilerWorker().compile(timeline, asset_paths, work_dir, final_output)
