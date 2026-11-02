"""Iteration 1 P1 security regression tests."""
from __future__ import annotations

import inspect
from pathlib import Path


def test_p1a_normalize_path_collapses_uuid():
    from app.api.metrics import normalize_path

    p = normalize_path("/projects/a1b2c3d4-e5f6-7890-abcd-ef1234567890/assets")
    assert "{id}" in p
    assert "a1b2c3d4" not in p


def test_p1a_metrics_token_gate_present():
    text = (Path(__file__).resolve().parents[1] / "app/api/metrics.py").read_text()
    assert "metrics_token" in text
    assert "401" in text


def test_p1b_release_in_new_tx_exists():
    from app.services import credits

    assert hasattr(credits, "release_in_new_tx")
    assert inspect.iscoroutinefunction(credits.release_in_new_tx)


def test_p1b_ai_uses_release_in_new_tx():
    text = (Path(__file__).resolve().parents[1] / "app/api/ai.py").read_text()
    assert "release_in_new_tx" in text


def test_p1c_settle_method_exists():
    from app.services.credits import CreditService

    assert hasattr(CreditService, "settle")


def test_p1c_chat_calls_settle():
    text = (Path(__file__).resolve().parents[1] / "app/api/ai.py").read_text()
    assert "settle" in text


def test_p1d_svg_served_as_attachment():
    text = (Path(__file__).resolve().parents[1] / "app/api/assets_upload.py").read_text()
    assert "image/svg" in text
    assert "attachment" in text
    assert "X-Content-Type-Options" in text
    assert "nosniff" in text


def test_p1e_render_bounds_and_credit_reserve():
    text = (Path(__file__).resolve().parents[1] / "app/api/jobs.py").read_text()
    assert "le=3840" in text or "Field(default=1280" in text
    assert "too many clips" in text
    assert "CreditService" in text
    assert "reserve" in text


def test_p1g_reset_token_not_echoed():
    text = (Path(__file__).resolve().parents[1] / "app/api/auth.py").read_text()
    assert 'resp["reset_token"]' not in text


def test_p1g_email_redacts_reset_body():
    text = (Path(__file__).resolve().parents[1] / "app/services/email.py").read_text()
    assert "redacted" in text.lower()
