import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "packages" / "ai-gateway"))

from app.services.ai_gateway import _make_provider, _provider_id_from_model, estimate_credits
from app.services.crypto import encrypt_secret, decrypt_secret


def test_provider_id_from_model():
    assert _provider_id_from_model("mock/default") == "mock"
    assert _provider_id_from_model("xai/grok-2") == "xai"
    assert _provider_id_from_model("openrouter/anthropic/claude") == "openrouter"
    assert _provider_id_from_model("grok-2-latest") == "xai"


def test_make_provider_mock():
    p = _make_provider("mock", None)
    assert p.id == "mock"


def test_make_provider_xai_with_key():
    p = _make_provider("xai", "test-key-not-used-until-call")
    assert p.id == "xai"
    assert p.api_key == "test-key-not-used-until-call"


def test_byok_encrypt_for_storage():
    raw = "sk-or-v1-example-key"
    blob = encrypt_secret(raw)
    assert decrypt_secret(blob) == raw


def test_estimate_still_works():
    from decimal import Decimal

    assert estimate_credits(1000, 0) == Decimal("1.0000")
