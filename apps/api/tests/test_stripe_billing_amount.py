"""P0.4 Stripe billing — amount match and no meta credits trust (source checks)."""
from pathlib import Path


def test_stripe_webhook_ignores_meta_credits_to_grant():
    text = (Path(__file__).resolve().parents[1] / "app" / "api" / "billing.py").read_text()
    assert "amount_mismatch" in text
    assert "currency_mismatch" in text
    assert "resolve_checkout_price" in text
    assert "not_paid" in text
    stripe_section = text[text.find("webhooks/stripe") : text.find("webhooks/yookassa")]
    assert "resolve_checkout_price" in stripe_section
    assert "grant = Decimal(str(cg))" not in stripe_section


def test_jobs_get_syncs_celery():
    text = (Path(__file__).resolve().parents[1] / "app" / "api" / "jobs.py").read_text()
    assert "sync_celery_job" in text
