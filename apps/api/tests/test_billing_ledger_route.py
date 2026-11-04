from pathlib import Path


def test_ledger_route_in_source():
    src = Path(__file__).resolve().parents[1] / "app" / "api" / "billing.py"
    text = src.read_text()
    assert "/ledger/{organization_id}" in text
    assert "list_ledger" in text
