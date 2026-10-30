import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "packages" / "ai-gateway"))

from vrav_ai.adapters.routerai import RouterAIProvider
from app.services.ai_gateway import _make_provider, _provider_id_from_model


def test_routerai_provider_id():
    p = RouterAIProvider(api_key="x")
    assert p.id == "routerai"
    assert p.capabilities.streaming is True
    assert p.capabilities.structured_output is False


def test_make_provider_routerai():
    p = _make_provider("routerai", "key")
    assert p.id == "routerai"
    assert p.api_key == "key"


def test_provider_id_routerai_model():
    assert _provider_id_from_model("routerai/gpt-test") == "routerai"
