from __future__ import annotations

import os
from unittest.mock import patch

from app.services.license_policy import PLAN_CAPS, allow_admin_license_issue, resolve_plan_caps


def test_plan_caps_bound_installations():
    assert PLAN_CAPS["selfhosted"]["max_installations"] <= 3
    assert "desktop" in PLAN_CAPS["selfhosted"]["features"]


def test_admin_issue_flag_default_off():
    with patch.dict(os.environ, {"ALLOW_ADMIN_LICENSE_ISSUE": ""}, clear=False):
        assert allow_admin_license_issue() is False


def test_admin_issue_flag_on():
    with patch.dict(os.environ, {"ALLOW_ADMIN_LICENSE_ISSUE": "1"}, clear=False):
        assert allow_admin_license_issue() is True


def test_resolve_unknown_plan_defaults():
    pid, n, feat = resolve_plan_caps("hacked_unlimited")
    assert pid == "selfhosted"
    assert n <= 3
