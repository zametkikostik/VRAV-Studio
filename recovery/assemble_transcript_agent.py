#!/usr/bin/env python3
"""Assemble transcript_agent.py from recovery parts. Run from repo root."""
from pathlib import Path
import hashlib
parts = [Path(f"recovery/agent_parts/part{i}.txt").read_text() for i in range(4)]
out = Path("apps/api/app/services/transcript_agent.py")
text = "".join(parts)
out.write_text(text)
h = hashlib.sha256(text.encode()).hexdigest()
assert h == "a68c9d4c70afe59b56da83243b5fd395e132f6c2fa56dffd08cb44875cd29a0c", h
print("OK", out, len(text), h)
