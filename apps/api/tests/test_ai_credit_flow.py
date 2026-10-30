from decimal import Decimal

from app.services.ai_gateway import estimate_credits


def test_estimate_credits():
    assert estimate_credits(0, 0) == Decimal("0.0000")
    assert estimate_credits(1000, 0) == Decimal("1.0000")
    assert estimate_credits(500, 500) == Decimal("1.0000")
