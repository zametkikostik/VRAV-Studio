"""P0.4 Stripe billing — amount match and no meta credits trust (source checks)."""
from pathlib import Path


def test_stripe_webhook_ignores_meta_credits_to_grant():
    api = Path(__file__).resolve().parents[1] / "app" / "api"
    text = "\n".join(
        (api / name).read_text()
        for name in ("billing.py", "billing_checkout.py", "billing_yookassa.py")
        if (api / name).exists()
    )
    grant = (Path(__file__).resolve().parents[1] / "app" / "services" / "billing_grant.py").read_text()
    text = text + "\n" + grant
    assert "amount_mismatch" in text
    assert "currency_mismatch" in text
    assert "amount_missing" in text
    assert "currency_missing" in text
    assert "resolve_checkout_price" in text
    assert "not_paid" in text
    stripe_src = (api / "billing_checkout.py").read_text()
    assert "webhooks/stripe" in stripe_src or "stripe_webhook" in stripe_src
    assert "grant_paid_order_credits" in stripe_src
    assert "grant = Decimal(str(cg))" not in stripe_src
    assert "order_snapshot" in grant


def test_jobs_get_syncs_celery():
    text = (Path(__file__).resolve().parents[1] / "app" / "api" / "jobs.py").read_text()
    assert "sync_celery_job" in text
