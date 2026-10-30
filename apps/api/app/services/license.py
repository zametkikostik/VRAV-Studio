"""License issuance and verification for self-hosted Desktop installs."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.license import EntitlementRecord, License, LicenseInstallation
from app.services.license_keys import generate_license_key


class LicenseStatus(BaseModel):
    valid: bool
    status: str
    max_installations: int | None = None
    current_installations: int | None = None
    features: dict | None = None
    valid_until: datetime | None = None
    license_id: str | None = None
    organization_id: str | None = None


class LicenseService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def issue(
        self,
        *,
        organization_id: uuid.UUID | None = None,
        plan_id: str | None = "selfhosted",
        max_installations: int = 1,
        valid_until: datetime | None = None,
        features: dict | None = None,
        license_key: str | None = None,
    ) -> License:
        key = license_key or generate_license_key()
        existing = await self.db.execute(select(License).where(License.license_key == key))
        if existing.scalar_one_or_none():
            raise ValueError("license_key already exists")
        lic = License(
            id=uuid.uuid4(),
            organization_id=organization_id,
            license_key=key,
            plan_id=plan_id,
            max_installations=max_installations,
            valid_from=datetime.now(timezone.utc),
            valid_until=valid_until,
            status="active",
            features=features or {"desktop": True, "ai_chat": True},
        )
        self.db.add(lic)
        await self.db.flush()

        if organization_id and lic.features:
            for feature_key, val in lic.features.items():
                self.db.add(
                    EntitlementRecord(
                        id=uuid.uuid4(),
                        organization_id=organization_id,
                        source_type="license",
                        source_id=lic.id,
                        feature_key=feature_key,
                        value={"enabled": bool(val)} if not isinstance(val, dict) else val,
                        valid_until=valid_until,
                    )
                )
            await self.db.flush()
        return lic

    async def _count_active_installations(self, license_id: uuid.UUID) -> int:
        result = await self.db.execute(
            select(func.count())
            .select_from(LicenseInstallation)
            .where(
                LicenseInstallation.license_id == license_id,
                LicenseInstallation.is_active.is_(True),
            )
        )
        return int(result.scalar_one())

    async def verify(
        self,
        license_key: str,
        installation_id: str,
        machine_fingerprint: str | None = None,
        *,
        bind: bool = True,
    ) -> LicenseStatus:
        result = await self.db.execute(select(License).where(License.license_key == license_key))
        lic = result.scalar_one_or_none()
        if lic is None:
            return LicenseStatus(valid=False, status="not_found")

        if lic.status == "revoked":
            return LicenseStatus(valid=False, status="revoked", license_id=str(lic.id))

        now = datetime.now(timezone.utc)
        if lic.valid_until and lic.valid_until < now:
            return LicenseStatus(
                valid=False, status="expired", license_id=str(lic.id), valid_until=lic.valid_until
            )
        if lic.status != "active":
            return LicenseStatus(valid=False, status=lic.status, license_id=str(lic.id))

        inst_result = await self.db.execute(
            select(LicenseInstallation).where(
                LicenseInstallation.license_id == lic.id,
                LicenseInstallation.installation_id == installation_id,
            )
        )
        installation = inst_result.scalar_one_or_none()
        active_count = await self._count_active_installations(lic.id)

        if installation is not None:
            if not installation.is_active:
                if active_count >= lic.max_installations:
                    return LicenseStatus(
                        valid=False,
                        status="device_limit",
                        max_installations=lic.max_installations,
                        current_installations=active_count,
                        license_id=str(lic.id),
                    )
                installation.is_active = True
            installation.last_seen_at = now
            if machine_fingerprint:
                installation.machine_fingerprint = machine_fingerprint
            await self.db.flush()
            return LicenseStatus(
                valid=True,
                status="active",
                max_installations=lic.max_installations,
                current_installations=await self._count_active_installations(lic.id),
                features=lic.features,
                valid_until=lic.valid_until,
                license_id=str(lic.id),
                organization_id=str(lic.organization_id) if lic.organization_id else None,
            )

        if not bind:
            return LicenseStatus(
                valid=active_count < lic.max_installations,
                status="active" if active_count < lic.max_installations else "device_limit",
                max_installations=lic.max_installations,
                current_installations=active_count,
                features=lic.features,
                valid_until=lic.valid_until,
                license_id=str(lic.id),
            )

        if active_count >= lic.max_installations:
            return LicenseStatus(
                valid=False,
                status="device_limit",
                max_installations=lic.max_installations,
                current_installations=active_count,
                features=lic.features,
                valid_until=lic.valid_until,
                license_id=str(lic.id),
            )

        self.db.add(
            LicenseInstallation(
                id=uuid.uuid4(),
                license_id=lic.id,
                installation_id=installation_id,
                machine_fingerprint=machine_fingerprint,
                last_seen_at=now,
                is_active=True,
            )
        )
        await self.db.flush()
        return LicenseStatus(
            valid=True,
            status="active",
            max_installations=lic.max_installations,
            current_installations=active_count + 1,
            features=lic.features,
            valid_until=lic.valid_until,
            license_id=str(lic.id),
            organization_id=str(lic.organization_id) if lic.organization_id else None,
        )

    async def deactivate_installation(self, license_key: str, installation_id: str) -> bool:
        result = await self.db.execute(select(License).where(License.license_key == license_key))
        lic = result.scalar_one_or_none()
        if lic is None:
            return False
        inst = await self.db.execute(
            select(LicenseInstallation).where(
                LicenseInstallation.license_id == lic.id,
                LicenseInstallation.installation_id == installation_id,
            )
        )
        row = inst.scalar_one_or_none()
        if row is None:
            return False
        row.is_active = False
        await self.db.flush()
        return True

    async def revoke(self, license_key: str) -> License | None:
        result = await self.db.execute(select(License).where(License.license_key == license_key))
        lic = result.scalar_one_or_none()
        if lic is None:
            return None
        lic.status = "revoked"
        await self.db.flush()
        return lic
