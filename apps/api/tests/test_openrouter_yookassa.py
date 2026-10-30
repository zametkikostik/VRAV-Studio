import asyncio
from decimal import Decimal

from app.services.yookassa import CheckoutRequest, Money, YooKassaPaymentProvider


def test_yookassa_sandbox_checkout():
    async def _run():
        p = YooKassaPaymentProvider(shop_id="test", secret_key="test")
        session = await p.create_checkout(
            CheckoutRequest(
                organization_id="00000000-0000-0000-0000-000000000001",
                amount=Money(amount=Decimal("100.00"), currency="RUB"),
                success_url="https://x/s",
                cancel_url="https://x/c",
            )
        )
        assert session.provider == "yookassa"

    asyncio.run(_run())
