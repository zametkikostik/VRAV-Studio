"""Server-side license plan caps and admin issue flag."""
from __future__ import annotations

import os

PLAN_CAPS: dict[str, dict] = {
    "selfhosted": {"max_installations": 3, "features": {"desktop": True, "ai_chat": True}},
    "selfhosted_team": {
        "max_installations": 10,
        "features": {"desktop": True, "ai_chat": True, "collab": True},
    },
}


def allow_admin_license_issue() -> bool:
    return os.getenv("ALLOW_ADMIN_LICENSE_ISSUE", "").lower() in ("1", "true", "yes")


def resolve_plan_caps(plan_id: str) -> tuple[str, int, dict]:
    pid = plan_id if plan_id in PLAN_CAPS else "selfhosted"
    caps = PLAN_CAPS[pid]
    return pid, int(caps["max_installations"]), dict(caps["features"])
