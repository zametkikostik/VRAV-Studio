# Iteration 12 — Media Asset Intelligence Foundation

**Branch:** `feature/iteration-12-media-intelligence`  
**Baseline:** main after Iteration 11 (PR #25)

## Audit findings

| Capability | Pre-existing | Iter12 action |
|------------|--------------|---------------|
| FFprobe raw JSON | `media.probe()` | **normalize_probe** + merge into Asset.metadata_ |
| Celery `vrav.media.probe` | returns probe only | **+ `vrav.media.analyze`** persists to Asset |
| Transcript column | Asset.transcript | **apply_transcript_to_asset** + mock provider |
| Keyframes | none | **extract_keyframes** (ffmpeg argv, capped) |
| AI plan context | duration/transcript only | **width/height/fps/codecs/segments/keyframes** |
| Live ASR / multimodal vision | none | **DEFERRED (INFRA SCOPE)** |

## Evidence

| Item | Status |
|------|--------|
| Normalize probe unit tests | PASS (deterministic fixtures) |
| Path traversal rejection | PASS |
| Plan context enrichment | PASS |
| Mock transcription | PASS |
| Live FFprobe on real files in CI | DEFERRED if runner lacks ffmpeg binary |
| Live Whisper/cloud ASR | DEFERRED (INFRA SCOPE) |
| Semantic visual understanding | DEFERRED — keyframes only, no multimodal model |

## Explicit non-claims

- Keyframe JPEGs ≠ scene understanding.
- Mock transcription ≠ production ASR accuracy.
- Iteration 11 real plan generation remains in place (no silent heuristic fallback).
