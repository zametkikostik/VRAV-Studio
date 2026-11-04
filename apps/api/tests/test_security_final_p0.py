"""Final P0 security regression — double grant, license lock, worker beat task."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]


def test_stripe_and_yookassa_order_already_paid_guard():
    api = ROOT / "app/api"
    text = "\n".join(
        (api / name).read_text()
        for name in ("billing.py", "billing_checkout.py", "billing_yookassa.py")
        if (api / name).exists()
    )
    assert text.count("order_already_paid") >= 2
    assert "Payment.order_id == order.id" in text


def test_license_verify_uses_row_lock():
    text = (ROOT / "app/services/license.py").read_text()
    assert "with_for_update" in text


def test_worker_registers_release_stale_task():
    tasks = (REPO / "apps/worker/worker/tasks.py").read_text()
    beat = (REPO / "apps/worker/worker/celery_app.py").read_text()
    assert "vrav.credits.release_stale" in tasks
    assert "vrav.credits.release_stale" in beat
    assert "credits-release-stale" in beat


def test_jobs_sync_does_not_use_get_timeout():
    sync = (ROOT / "app/api/jobs_celery_sync.py").read_text()
    assert "AsyncResult" in sync
    assert "ar.get(" not in sync
    assert "async_result.get" not in sync
