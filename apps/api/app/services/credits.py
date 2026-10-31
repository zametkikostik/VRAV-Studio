from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import CreditAccount, CreditLedger, CreditReservation


class InsufficientCreditsError(Exception):
    pass


class CreditService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_or_create_account(self, organization_id: uuid.UUID) -> CreditAccount:
        result = await self.db.execute(
            select(CreditAccount).where(CreditAccount.organization_id == organization_id)
        )
        account = result.scalar_one_or_none()
        if account is None:
            account = CreditAccount(
                id=uuid.uuid4(),
                organization_id=organization_id,
                balance=Decimal("0"),
                reserved=Decimal("0"),
            )
            self.db.add(account)
            await self.db.flush()
        return account

    async def topup(
        self,
        organization_id: uuid.UUID,
        amount: Decimal,
        description: str = "topup",
        metadata: dict | None = None,
    ) -> CreditAccount:
        if amount <= 0:
            raise ValueError("amount must be positive")
        account = await self.get_or_create_account(organization_id)
        account.balance = account.balance + amount
        self.db.add(
            CreditLedger(
                account_id=account.id,
                entry_type="topup",
                amount=amount,
                balance_after=account.balance,
                description=description,
                metadata_=metadata,
            )
        )
        await self.db.flush()
        return account

    async def _lock_account(self, account_id: uuid.UUID) -> CreditAccount:
        result = await self.db.execute(
            select(CreditAccount).where(CreditAccount.id == account_id).with_for_update()
        )
        account = result.scalar_one()
        return account

    async def reserve(
        self,
        organization_id: uuid.UUID,
        amount: Decimal,
        *,
        job_id: uuid.UUID | None = None,
        idempotency_key: str | None = None,
    ) -> CreditReservation:
        if amount <= 0:
            raise ValueError("amount must be positive")
        if idempotency_key:
            existing = await self.db.execute(
                select(CreditReservation).where(CreditReservation.idempotency_key == idempotency_key)
            )
            row = existing.scalar_one_or_none()
            if row is not None:
                return row
        account = await self.get_or_create_account(organization_id)
        account = await self._lock_account(account.id)
        available = account.balance - account.reserved
        if available < amount:
            raise InsufficientCreditsError(
                f"Need {amount}, available {available} (balance={account.balance}, reserved={account.reserved})"
            )
        account.reserved = account.reserved + amount
        reservation = CreditReservation(
            id=uuid.uuid4(),
            account_id=account.id,
            amount=amount,
            status="pending",
            job_id=job_id,
            idempotency_key=idempotency_key,
        )
        self.db.add(reservation)
        self.db.add(
            CreditLedger(
                account_id=account.id,
                reservation_id=reservation.id,
                entry_type="reserve",
                amount=-amount,
                balance_after=account.balance,
                description="reserve",
            )
        )
        await self.db.flush()
        return reservation

    async def commit(self, reservation_id: uuid.UUID) -> CreditReservation:
        result = await self.db.execute(
            select(CreditReservation).where(CreditReservation.id == reservation_id)
        )
        reservation = result.scalar_one_or_none()
        if reservation is None:
            raise ValueError("reservation not found")
        if reservation.status != "pending":
            return reservation
        account = await self._lock_account(reservation.account_id)
        account.balance = account.balance - reservation.amount
        account.reserved = account.reserved - reservation.amount
        if account.balance < 0 or account.reserved < 0:
            raise RuntimeError("credit accounting invariant broken")
        reservation.status = "committed"
        self.db.add(
            CreditLedger(
                account_id=account.id,
                reservation_id=reservation.id,
                entry_type="commit",
                amount=-reservation.amount,
                balance_after=account.balance,
                description="commit",
            )
        )
        await self.db.flush()
        return reservation

    async def release(self, reservation_id: uuid.UUID) -> CreditReservation:
        result = await self.db.execute(
            select(CreditReservation).where(CreditReservation.id == reservation_id)
        )
        reservation = result.scalar_one_or_none()
        if reservation is None:
            raise ValueError("reservation not found")
        if reservation.status != "pending":
            return reservation
        account = await self._lock_account(reservation.account_id)
        account.reserved = account.reserved - reservation.amount
        if account.reserved < 0:
            raise RuntimeError("credit accounting invariant broken")
        reservation.status = "released"
        self.db.add(
            CreditLedger(
                account_id=account.id,
                reservation_id=reservation.id,
                entry_type="release",
                amount=reservation.amount,
                balance_after=account.balance,
                description="release",
            )
        )
        await self.db.flush()
        return reservation

    async def release_stale_reservations(self, older_than_seconds: int = 3600) -> int:
        """Release pending reservations older than TTL. Idempotent per row."""
        from datetime import datetime, timedelta, timezone

        from app.models.billing import CreditReservation as CR

        cutoff = datetime.now(timezone.utc) - timedelta(seconds=older_than_seconds)
        result = await self.db.execute(
            select(CR).where(CR.status == "pending", CR.created_at < cutoff)
        )
        n = 0
        for res in list(result.scalars().all()):
            try:
                await self.release(res.id)
                n += 1
            except Exception:
                continue
        return n
