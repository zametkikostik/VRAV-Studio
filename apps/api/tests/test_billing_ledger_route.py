from pathlib import Path


def test_ledger_route_in_source():
    api_dir = Path(__file__).resolve().parents[1] / "app" / "api"
    billing = (api_dir / "billing.py").read_text()
    ledger = (api_dir / "billing_ledger.py").read_text() if (api_dir / "billing_ledger.py").exists() else ""
    combined = billing + "\n" + ledger
    assert "list_ledger" in combined
    assert "zlib" not in billing
    assert "b64decode" not in billing
    assert "exec(" not in billing


def test_billing_module_still_has_core_routes():
    """Guard: billing package must expose plans/credits/webhooks (readable modules)."""
    api_dir = Path(__file__).resolve().parents[1] / "app" / "api"
    texts = []
    for name in (
        "billing.py",
        "billing_plans.py",
        "billing_checkout.py",
        "billing_yookassa.py",
        "billing_ledger.py",
    ):
        p = api_dir / name
        if p.exists():
            texts.append(p.read_text())
    joined = "\n".join(texts)
    assert "list_plans" in joined or '@router.get("/plans")' in joined
    assert "topup_credits" in joined or "credits/topup" in joined
    assert "stripe_webhook" in joined
    assert "yookassa_webhook" in joined
    try:
        from app.api import billing as billing_mod

        paths = [getattr(r, "path", "") or "" for r in billing_mod.router.routes]
        assert any("plans" in p for p in paths)
        assert any("stripe" in p for p in paths)
        assert any("yookassa" in p for p in paths)
    except ModuleNotFoundError:
        pass
