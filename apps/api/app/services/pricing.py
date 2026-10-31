"""Server-side pricing — never trust client-submitted amounts for checkout."""
from __future__ import annotations

from decimal import Decimal
from typing import Any


BUILTIN_PLANS: dict[str, dict[str, Any]] = {
    "credits_100": {
        "name": "100 Credits",
        "price": Decimal("10.0000"),
        "currency": "USD",
        "credits": Decimal("100.0000"),
        "kind": "credits",
    },
    "credits_500": {
        "name": "500 Credits",
        "price": Decimal("40.0000"),
        "currency": "USD",
        "credits": Decimal("500.0000"),
        "kind": "credits",
    },
    "pro_monthly": {
        "name": "Pro Monthly",
        "price": Decimal("29.0000"),
        "currency": "USD",
        "credits": Decimal("300.0000"),
        "kind": "subscription",
    },
    "selfhosted": {
        "name": "Self-hosted License",
        "price": Decimal("199.0000"),
        "currency": "USD",
        "credits": Decimal("0"),
        "kind": "license",
    },
}


class PricingError(Exception):
    pass


class PricedItem:
    def __init__(
        self,
        plan_id: str,
        amount: Decimal,
        currency: str,
        credits_to_grant: Decimal,
        kind: str,
        name: str,
    ):
        self.plan_id = plan_id
        self.amount = amount
        self.currency = currency
        self.credits_to_grant = credits_to_grant
        self.kind = kind
        self.name = name


async def resolve_checkout_price(
    db: object,
    *,
    plan_id: str | None,
    client_amount: Decimal | None = None,
    client_currency: str | None = None,
) -> PricedItem:
    if not plan_id:
        raise PricingError("plan_id is required; client-specified amounts are not accepted")

    plan = None
    try:
        from sqlalchemy import select
        from app.models.billing import TariffPlan

        result = await db.execute(  # type: ignore[attr-defined]
            select(TariffPlan).where(TariffPlan.id == plan_id, TariffPlan.is_active.is_(True))
        )
        plan = result.scalar_one_or_none()
    except Exception:
        plan = None

    if plan is not None:
        priced = PricedItem(
            plan_id=plan.id,
            amount=Decimal(plan.price_monthly),
            currency=plan.currency or "USD",
            credits_to_grant=Decimal(plan.included_credits or 0),
            kind="subscription",
            name=plan.name,
        )
    elif plan_id in BUILTIN_PLANS:
        b = BUILTIN_PLANS[plan_id]
        priced = PricedItem(
            plan_id=plan_id,
            amount=Decimal(b["price"]),
            currency=str(b["currency"]),
            credits_to_grant=Decimal(b["credits"]),
            kind=str(b["kind"]),
            name=str(b["name"]),
        )
    else:
        raise PricingError(f"unknown or inactive plan_id: {plan_id}")

    if client_amount is not None and abs(client_amount - priced.amount) > Decimal("0.0001"):
        raise PricingError(
            f"amount mismatch: client sent {client_amount}, server price is {priced.amount}"
        )
    if client_currency and client_currency.upper() != priced.currency.upper():
        raise PricingError(
            f"currency mismatch: client sent {client_currency}, server expects {priced.currency}"
        )
    return priced
