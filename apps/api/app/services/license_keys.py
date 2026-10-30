"""Pure license key helpers (no DB)."""
from __future__ import annotations

import secrets


def generate_license_key() -> str:
    parts = [secrets.token_hex(2).upper() for _ in range(4)]
    return "VRAV-" + "-".join(parts)
