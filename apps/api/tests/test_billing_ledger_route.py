from pathlib import Path


def test_ledger_route_in_source():
    api_dir = Path(__file__).resolve().parents[1] / "app" / "api"
    billing = (api_dir / "billing.py").read_text()
    ledger_path = api_dir / "billing_ledger.py"
    ledger = ledger_path.read_text() if ledger_path.exists() else ""
    combined = billing + "\n" + ledger
    assert "/ledger/{organization_id}" in combined
    assert "list_ledger" in combined


def test_billing_module_still_has_core_routes():
    """Guard against accidental truncation of apps/api/app/api/billing.py."""
    src = Path(__file__).resolve().parents[1] / "app" / "api" / "billing.py"
    text = src.read_text()
    assert len(text) > 5000, "billing.py looks truncated"
    assert "list_plans" in text or '@router.get("/plans")' in text
    assert "topup_credits" in text or "credits/topup" in text
    assert "stripe_webhook" in text
    assert "yookassa_webhook" in text
