# Iteration 13 — Media Intelligence API & Job Lifecycle

**Branch:** `feature/iteration-13-media-job-integration`

## Audit map (reuse)

| Component | Reused |
|-----------|--------|
| Job model + JobOut + GET /jobs/{id} | yes |
| jobs_celery_sync | extended for analyze/transcribe |
| Celery `vrav.media.analyze` / `transcribe` | yes (Iter12) |
| AI plan context (Iter11/12) | preserved |

## Delivered

| Item | Status |
|------|--------|
| POST /jobs/analyze | implemented |
| POST /jobs/transcribe | implemented |
| Org/project/asset authorization | implemented |
| Job row before Celery dispatch | implemented |
| Sync treats error payload as failed | implemented |
| Time-based keyframe timestamps | implemented |
| Transcription provider gate (no silent mock in production) | implemented |
| Live ASR provider | DEFERRED (INFRA SCOPE) |
| Semantic visual understanding | DEFERRED (not claimed) |

## Non-claims

- Mock transcription only when ENVIRONMENT=test/ci or TRANSCRIPTION_PROVIDER=mock.
- Keyframes are samples, not scene detection.
