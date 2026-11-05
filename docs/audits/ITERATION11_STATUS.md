# Iteration 11 — Real AI Editing Plan

**Branch:** `feature/iteration-11-real-ai-editing-plan`  
**Baseline main:** `ed1be9f`

## Architectural decisions

- Reuse existing `POST /editing/plans/generate`, `EditingPlan` IR, `apply` path, AI Gateway `run_chat`, CreditService reserve/commit/release.
- No second AI gateway or timeline format.
- Provider failures and invalid JSON **must not** fall back to heuristics (removed silent `llm_fallback_heuristics`).
- Asset context includes filename, type, `duration_ms` from metadata (when present), transcript snippet (when present). Never invents IDs or quotes.
- Server re-validates membership, source windows, clip/duration limits after model output.

## Evidence

| Item | Status |
|------|--------|
| Deterministic mock + fake chat_fn unit tests | PASS (local pytest) |
| Live provider sandbox (xAI/OpenRouter with real keys) | DEFERRED (INFRA SCOPE) |
| Visual frame understanding | DEFERRED (not implemented; limitations flag) |
| Transcript-based planning | PARTIAL — uses transcript when stored; no auto-transcribe job in this slice |
| Frontend preview + apply | PASS (existing PlanRenderPanel; mode follows NEXT_PUBLIC_AI_MODEL) |
| Credit reserve on LLM path; release on failure | PASS (existing endpoint logic retained) |

## Known limitations

- Duration only from `Asset.metadata_` keys; probe pipeline may not always populate it.
- Transcript must already be on Asset; no Whisper job in Iter11.
- Live BYOK verification requires secrets not present in CI.
