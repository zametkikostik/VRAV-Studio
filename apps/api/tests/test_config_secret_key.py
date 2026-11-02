"""Fix 1: SECRET_KEY validation in Settings."""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from pydantic import ValidationError


def test_production_rejects_empty_secret_key():
    from app.core.config import Settings

    with patch.dict(os.environ, {"ENVIRONMENT": "production", "SECRET_KEY": ""}, clear=False):
        os.environ["SECRET_KEY"] = ""
        with pytest.raises((ValidationError, ValueError)):
            Settings(_env_file=None)


def test_production_rejects_known_default_secret():
    from app.core.config import Settings

    with patch.dict(
        os.environ,
        {"ENVIRONMENT": "production", "SECRET_KEY": "dev-secret-change-me"},
        clear=False,
    ):
        with pytest.raises((ValidationError, ValueError)):
            Settings(_env_file=None)


def test_development_accepts_explicit_secret():
    from app.core.config import Settings

    with patch.dict(
        os.environ,
        {"ENVIRONMENT": "development", "SECRET_KEY": "ci-secret-key-for-tests-xxxxxxxx"},
        clear=False,
    ):
        s = Settings(_env_file=None)
        assert s.secret_key == "ci-secret-key-for-tests-xxxxxxxx"


def test_development_auto_generates_when_empty():
    from app.core.config import Settings

    with patch.dict(os.environ, {"ENVIRONMENT": "development", "SECRET_KEY": ""}, clear=False):
        os.environ["SECRET_KEY"] = ""
        s = Settings(_env_file=None)
        assert len(s.secret_key) >= 32
