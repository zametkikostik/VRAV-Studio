# Iteration 3 — AI Director / Timeline compile

## Delivered

| Item | Status | Location |
|------|--------|----------|
| `TimelineDefinition` contract | PASS | `apps/api/app/services/timeline_definition.py` |
| JSON Schema export | PASS | `timeline_json_schema()` |
| Asset `transcript` + `embedding` | PASS | model + Alembic `012` |
| `FFmpegCompilerWorker` skeleton | PASS | `apps/api/app/services/ffmpeg_compiler.py` |
| Unit tests | PASS | `tests/test_iteration3_timeline.py` |

## Notes

- `TimelineDefinition` extends existing `EditingPlan` (no parallel IR).
- Compiler emits **argv lists only** (no shell strings).
- `embedding` is JSONB float array (1536 recommended); pgvector index is ops follow-up.
- Apply DB: `alembic upgrade head` (revision 012).

## Local verify

```bash
cd apps/api && env -u DATABASE_URL -u REDIS_URL \
  PYTHONPATH=".:../../packages/ai-gateway:../../packages/core" \
  SECRET_KEY=ci-secret-key-for-tests python -m pytest -q tests/
```
