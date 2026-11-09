# Phase C.2.3 Source Recovery

## Status

- `apps/api/tests/test_phase_c23_api_security_closure.py` — **RESTORED** on this branch (SHA-256 `5b735f921d735cfdcfc73af1adccb1f14acadb9df4d9ce7b38c0e183085165df`).
- `apps/api/app/services/transcript_agent.py` — still truncated on remote; full source is in `recovery/agent_parts/`.

## Assemble transcript_agent.py

From repository root (authenticated machine):

```bash
python3 recovery/assemble_transcript_agent.py
# or:
# cat recovery/agent_parts/part{0,1,2,3}.txt > apps/api/app/services/transcript_agent.py

git add apps/api/app/services/transcript_agent.py
git commit -m "fix(phase-c23): restore complete transcript_agent.py from recovery parts"
git push origin fix/phase-c23-api-security-closure
```

Expected SHA-256 after assembly:
`a68c9d4c70afe59b56da83243b5fd395e132f6c2fa56dffd08cb44875cd29a0c`

Do not merge PR #47 until both files are complete and CI is green.
