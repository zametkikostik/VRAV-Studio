from pathlib import Path


def test_ledger_route_in_source():
    api_dir = Path(__file__).resolve().parents[1] / "app" / "api"
    billing = (api_dir / "billing.py").read_text()
    ledger_path = api_dir / "billing_ledger.py"
    ledger = ledger_path.read_text() if ledger_path.exists() else ""
    combined = billing + "\n" + ledger
    assert "list_ledger" in combined


def test_billing_module_still_has_core_routes():
    """Guard: billing router must expose plans/credits/webhooks."""
    from app.api import billing as billing_mod

    paths = [getattr(r, "path", "") or "" for r in billing_mod.router.routes]
    joined = " ".join(paths)
    assert any("plans" in p for p in paths) or "plans" in joined
    assert any("topup" in p or "credits" in p for p in paths)
    assert any("stripe" in p for p in paths)
    assert any("yookassa" in p for p in paths)
