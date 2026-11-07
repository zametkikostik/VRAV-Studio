# Live ASR Engine V1

## Providers
| Value of `TRANSCRIPTION_PROVIDER` | Requirements |
|-----------------------------------|--------------|
| `mock` | CI / local deterministic |
| `openai` / `whisper` | `OPENAI_API_KEY` |
| `deepgram` | `DEEPGRAM_API_KEY` |

Keys stay server-side. Never sent to the browser.

## Pipeline
1. Celery `vrav.media.transcribe`
2. Resolve storage path (no client paths)
3. FFmpeg extract mono 16 kHz WAV (`extract_audio_for_asr`)
4. Provider HTTP call (httpx) with bounded retries
5. Normalize segments → `validate_transcript_payload`
6. Persist on Asset (`transcript` + `metadata.transcription`)

## Real provider tests
Opt-in only. Without credentials, live integration is **DEFERRED (INFRA SCOPE)**.
CI uses mocks exclusively.
