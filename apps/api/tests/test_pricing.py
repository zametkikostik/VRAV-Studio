import asyncio
from decimal import Decimal

from app.services.pricing import BUILTIN_PLANS, PricingError, resolve_checkout_price


class _FakeResult:
    def scalar_one_or_none(self):
        return None


class _FakeDB:
    async def execute(self, *a, **k):
        return _FakeResult()


def test_builtin_credits_100():
    priced = asyncio.new_event_loop().run_until_complete(
        resolve_checkout_price(_FakeDB(), plan_id="credits_100")
    )
    assert priced.amount == Decimal("10.0000")
    assert priced.credits_to_grant == Decimal("100.0000")


def test_rejects_unknown_plan():
    try:
        asyncio.new_event_loop().run_until_complete(
            resolve_checkout_price(_FakeDB(), plan_id="no_such_plan")
        )
        assert False
    except PricingError:
        pass


def test_rejects_missing_plan_id():
    try:
        asyncio.new_event_loop().run_until_complete(
            resolve_checkout_price(_FakeDB(), plan_id=None)
        )
        assert False
    except PricingError:
        pass


def test_rejects_amount_mismatch():
    try:
        asyncio.new_event_loop().run_until_complete(
            resolve_checkout_price(_FakeDB(), plan_id="credits_100", client_amount=Decimal("1.00"))
        )
        assert False
    except PricingError as e:
        assert "mismatch" in str(e).lower()


def test_accepts_matching_client_amount():
    priced = asyncio.new_event_loop().run_until_complete(
        resolve_checkout_price(_FakeDB(), plan_id="credits_100", client_amount=Decimal("10.0000"))
    )
    assert priced.amount == Decimal("10.0000")


def test_builtin_catalog_has_expected_keys():
    assert "credits_100" in BUILTIN_PLANS
    assert "pro_monthly" in BUILTIN_PLANS
