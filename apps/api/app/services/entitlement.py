"""Entitlement Service: subscriptions + licenses + credits."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import CreditAccount, Subscription, TariffPlan
from app.models.license import EntitlementRecord, License


class EntitlementService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_active_subscription(self, organization_id: uuid.UUID) -> Subscription | None:
        result = await self.db.execute(
            select(Subscription).where(
                Subscription.organization_id == organization_id,
                Subscription.status.in_(["active", "trialing"]),
            )
        )
        return result.scalars().first()

    async def available_credits(self, organization_id: uuid.UUID) -> Decimal:
        result = await self.db.execute(
            select(CreditAccount).where(CreditAccount.organization_id == organization_id)
        )
        account = result.scalar_one_or_none()
        if account is None:
            return Decimal("0")
        return account.balance - account.reserved

    async def has_feature(self, organization_id: uuid.UUID, feature_key: str) -> bool:
        sub = await self.get_active_subscription(organization_id)
        if sub is not None:
            plan = await self.db.get(TariffPlan, sub.plan_id)
            if plan and plan.features and plan.features.get(feature_key):
                return True

        now = datetime.now(timezone.utc)
        result = await self.db.execute(
            select(EntitlementRecord).where(
                EntitlementRecord.organization_id == organization_id,
                EntitlementRecord.feature_key == feature_key,
            )
        )
        for rec in result.scalars().all():
            if rec.valid_until and rec.valid_until < now:
                continue
            val = rec.value or {}
            if val.get("enabled", True):
                return True

        lic_result = await self.db.execute(
            select(License).where(
                License.organization_id == organization_id,
                License.status == "active",
            )
        )
        for lic in lic_result.scalars().all():
            if lic.valid_until and lic.valid_until < now:
                continue
            if lic.features and lic.features.get(feature_key):
                return True

        return False
