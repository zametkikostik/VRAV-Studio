"""Iteration 10: Stripe/YooKassa grant outcome consistency (source + unit)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_stripe_handles_all_grant_rejection_reasons():
    text = (ROOT / "app/api/billing_checkout.py").read_text()
    assert 'if reason == "granted"' in text
    assert 'return _finish("processed"' in text
    assert 'return _finish("ignored", reason' in text
    assert "order_already_paid" in text
    assert "_finish" in text


def test_yookassa_and_stripe_share_outcome_vocabulary():
    stripe = (ROOT / "app/api/billing_checkout.py").read_text()
    yk = (ROOT / "app/api/billing_yookassa.py").read_text()
    for token in (
        'return _finish("processed"',
        'return _finish("already_processed"',
        'return _finish("ignored"',
        "processed_at is not None",
        "processing_error",
    ):
        assert token in stripe, token
        assert token in yk, token


def test_webhook_event_not_marked_processed_on_insert():
    stripe = (ROOT / "app/api/billing_checkout.py").read_text()
    assert "processed_at=None" in stripe
    yk = (ROOT / "app/api/billing_yookassa.py").read_text()
    assert "processed_at=None" in yk
