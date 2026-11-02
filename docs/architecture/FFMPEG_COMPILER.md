# FFmpegCompilerWorker — architecture

Status: Iteration 3 skeleton (argv-only). Iteration 4 extends filters (video concat / audio mix / overlays).

## Pipeline

```
TimelineDefinition (JSON / Pydantic)
        |
        v
  validate_timeline()     <- same rules as EditingPlan
        |
        v
  plan_to_render_clips()  <- currently video track_type only
        |
        v
  asset_id -> filesystem path map (caller-supplied)
        |
        v
  FFmpegCompilerWorker.compile()
        |
        +-- per-clip segment argv  (trim + scale/pad + encode)
        +-- optional concat argv   (concat demuxer, multi-clip)
        |
        v
  CompiledTimeline { segments[], concat_argv?, final_output }
        |
        v
  Executor (services/render.py / Celery) runs argv lists with subprocess, shell=False
```

## Why argv lists, never a shell string

| Risk | Mitigation |
|------|------------|
| Command injection via filenames / titles | Paths and text are separate argv elements; no `shell=True`, no `os.system` |
| Accidental metacharacters (`|`, `;`, `&&`) | Never interpolated into one string |
| Reviewability | Each flag is an explicit list entry |

The compiler **only builds** `list[str]`. Execution is the executor's job.

## Track mapping (contract)

`PlanClip.track_type` / `TimelineClip.track_type` (from `editing_plan.py`):

| `track_type` | Semantic lane | Compiler (Iter 3) | Compiler (Iter 4 target) |
|--------------|---------------|-------------------|---------------------------|
| `video` | primary picture | **used** | concat / xfade / normalize |
| `audio` | sound beds / VO | **ignored** by `plan_to_render_clips` | trim / volume / amix / afade |
| `overlay` | titles / graphics | **ignored** for media compile | drawtext / overlay |

Numeric lane convention for docs and future filter graphs:

- **0** — video
- **1** — audio
- **2** — graphics / overlay

Subtitles live in `TimelineDefinition.subtitles[]` (not clips); Iter 3 does not emit drawtext yet.

## Input example (TimelineDefinition JSON)

```json
{
  "version": "1.0",
  "project_id": "11111111-1111-1111-1111-111111111111",
  "source_asset_ids": [
    "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
  ],
  "clips": [
    {
      "asset_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
      "track_type": "video",
      "source_in_ms": 0,
      "duration_ms": 2000,
      "timeline_start_ms": 0
    },
    {
      "asset_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
      "track_type": "video",
      "source_in_ms": 500,
      "duration_ms": 1500,
      "timeline_start_ms": 2000
    }
  ],
  "subtitles": [],
  "output": {
    "width": 1280,
    "height": 720,
    "fps": 30,
    "video_codec": "libx264",
    "audio_codec": "aac",
    "container": "mp4"
  }
}
```

## Output example (argv)

For **one** video clip, a single segment targets `final_output` directly:

```text
ffmpeg -y -hide_banner -loglevel error
  -i /storage/org/a.mp4
  -t 2.000
  -vf scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2
  -r 30
  -c:v libx264 -c:a aac -movflags +faststart
  /out/final.mp4
```

For **two or more** video clips:

1. Segment N -> `work_dir/seg_NNNN.mp4` (trim via `-ss` / `-t`, normalize scale/pad/fps).
2. Concat demuxer step (executor must write `concat.txt` listing segments first — noted in `CompiledTimeline.notes`):

```text
ffmpeg -y -hide_banner -loglevel error
  -f concat -safe 0 -i /work/concat.txt
  -c copy
  /out/final.mp4
```

`CompiledTimeline.all_argv()` returns the ordered list of these argv vectors.

## Path resolution

- Paths come only from the caller's `asset_paths: dict[asset_id, path]`.
- Missing `asset_id` -> `CompileError`.
- Iteration 4 adds explicit path-traversal rejection on resolved paths before they enter argv.

## Related modules

| Module | Role |
|--------|------|
| `timeline_definition.py` | Contract + `validate_timeline` + JSON Schema |
| `editing_plan.py` | Shared IR (`PlanClip`, `validate_plan`, `plan_to_render_clips`) |
| `ffmpeg_compiler.py` | Argv builder |
| `render.py` | Executor that runs FFmpeg |

## Known gaps (closed in Iteration 4 code task)

- Audio / overlay clips not compiled
- No filter_complex concat / xfade / amix yet (concat demuxer only)
- Subtitles not mapped to drawtext
- No path-traversal guard inside the compiler
