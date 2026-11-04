"""P0.4 Stripe billing — amount match and no meta credits trust (source checks)."""
from pathlib import Path


def test_stripe_webhook_ignores_meta_credits_to_grant():
    api = Path(__file__).resolve().parents[1] / "app" / "api"
    text = "\n".join(
        (api / name).read_text()
        for name in ("billing.py", "billing_checkout.py", "billing_yookassa.py")
        if (api / name).exists()
    )
    assert "amount_mismatch" in text
    assert "currency_mismatch" in text
    assert "resolve_checkout_price" in text
    assert "not_paid" in text
    # Stripe section lives in billing_checkout after modular split
    stripe_src = (api / "billing_checkout.py").read_text() if (api / "billing_checkout.py").exists() else text
    assert "webhooks/stripe" in stripe_src or "stripe_webhook" in stripe_src
    assert "resolve_checkout_price" in stripe_src
    assert "grant = Decimal(str(cg))" not in stripe_src


def test_jobs_get_syncs_celery():
    text = (Path(__file__).resolve().parents[1] / "app" / "api" / "jobs.py").read_text()
    assert "sync_celery_job" in text
