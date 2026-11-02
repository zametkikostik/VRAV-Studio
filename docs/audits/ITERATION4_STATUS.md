# Iteration 4 — Media Pipeline Completion

## Status: COMPLETE (unit-verified)

| Metric | Value |
|--------|-------|
| Tests before Iter 4 | 192 |
| Tests after Task 1 docs | 194 |
| Tests after Task 2 compiler | **200 passed** |

## Commits

| Task | Commit message | Contents |
|------|----------------|----------|
| 1 | `docs(iter4): FFMPEG_COMPILER architecture` | `docs/architecture/FFMPEG_COMPILER.md` |
| 2 | `feat(iter4): FFmpegCompiler video/audio/overlay...` | `ffmpeg_compiler.py`, tests |
| 3 | this status | `ITERATION4_STATUS.md` |

## Added / changed

| File | Change |
|------|--------|
| `docs/architecture/FFMPEG_COMPILER.md` | Pipeline, argv safety, track lanes, examples |
| `apps/api/app/services/ffmpeg_compiler.py` | filter_complex: concat, xfade, drawtext, overlay, atrim/volume/amix/afade/loudnorm; `safe_media_path` |
| `apps/api/app/services/editing_plan.py` | optional `PlanClip.effects` |
| `apps/api/tests/test_iteration4_media.py` | 6 media tests |
| `apps/api/tests/test_iteration4_docs.py` | doc presence |

## Capabilities

- Video: trim, scale/pad/setsar/fps, concat filter, optional xfade
- Audio: atrim, volume, loudnorm, afade, amix
- Overlay: drawtext (titles), image overlay
- Subtitles: drawtext with enable window
- Security: argv-only; path traversal rejected

## Known limitations

- Executor remains in `services/render.py` (compiler does not run FFmpeg)
- No GPU / hardware encode filters
- `embedding` still JSONB (Iteration 5 / ops)
- Multi-clip xfade only for exactly 2 video clips when `effects.xfade_ms` set
- `PlanClip.effects` is a free-form dict (not a strict schema yet)

## Verify

```bash
cd apps/api && env -u DATABASE_URL -u REDIS_URL \
  PYTHONPATH=".:../../packages/ai-gateway:../../packages/core" \
  SECRET_KEY=ci-secret-key-for-tests python -m pytest -q tests/
```
