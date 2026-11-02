"""Compile TimelineDefinition into FFmpeg argument vectors (no shell).

Skeleton worker: builds argv lists that render_timeline / Celery can execute.
Does not run ffmpeg itself unless an executor consumes the argv lists.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.services.editing_plan import plan_to_render_clips
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

    def all_argv(self) -> list[list[str]]:
        cmds = [s.argv for s in self.segments]
        if self.concat_argv:
            cmds.append(self.concat_argv)
        return cmds


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

        clips = plan_to_render_clips(tl)
        if not clips:
            raise CompileError("timeline has no clips")

        w = tl.output.width
        h = tl.output.height
        fps = float(tl.output.fps)
        vcodec = tl.output.video_codec or "libx264"
        acodec = tl.output.audio_codec or "aac"

        segments: list[CompiledSegment] = []
        notes: list[str] = []

        for i, clip in enumerate(clips):
            aid = str(clip.get("asset_id") or "")
            if aid not in asset_paths:
                raise CompileError(f"missing asset path for asset_id={aid}")
            src = Path(asset_paths[aid])
            seg_out = work / f"seg_{i:04d}.mp4"
            argv: list[str] = [
                self.ffmpeg_bin,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
            ]
            source_in = int(clip.get("source_in_ms") or 0)
            if source_in > 0:
                argv += ["-ss", f"{source_in / 1000.0:.3f}"]
            argv += ["-i", str(src)]
            dur = clip.get("duration_ms")
            if dur is not None and int(dur) > 0:
                argv += ["-t", f"{int(dur) / 1000.0:.3f}"]
            argv += [
                "-vf",
                f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
                f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2",
                "-r",
                str(fps),
                "-c:v",
                vcodec,
                "-c:a",
                acodec,
                "-movflags",
                "+faststart",
                str(seg_out),
            ]
            segments.append(CompiledSegment(index=i, argv=argv, output=seg_out))

        if len(segments) == 1:
            segments[0].argv[-1] = str(out)
            segments[0].output = out
            return CompiledTimeline(
                segments=segments,
                concat_argv=None,
                final_output=out,
                width=w,
                height=h,
                fps=fps,
                notes=notes,
            )

        list_file = work / "concat.txt"
        concat_argv = [
            self.ffmpeg_bin,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_file),
            "-c",
            "copy",
            str(out),
        ]
        notes.append(f"write concat list to {list_file} with segments before concat")
        return CompiledTimeline(
            segments=segments,
            concat_argv=concat_argv,
            final_output=out,
            width=w,
            height=h,
            fps=fps,
            notes=notes,
        )


def compile_timeline(
    timeline: TimelineDefinition | dict[str, Any],
    asset_paths: dict[str, str | Path],
    work_dir: str | Path,
    final_output: str | Path,
) -> CompiledTimeline:
    return FFmpegCompilerWorker().compile(timeline, asset_paths, work_dir, final_output)
