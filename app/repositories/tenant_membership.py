from __future__ import annotations

from uuid import UUID

from sqlalchemy import Select, select

from app.db.models.tenant_membership import TenantMembership
from app.repositories.base import TenantScopedRepository


class TenantMembershipRepository(TenantScopedRepository):
    async def get_by_id(
        self,
        membership_id: UUID,
    ) -> TenantMembership | None:
        statement: Select[TenantMembership] = self._scope(
            select(TenantMembership),
            TenantMembership.tenant_id,
        ).where(TenantMembership.id == membership_id)

        result = await self._session.scalars(statement)

        return result.first()

    async def list_for_user(
        self,
        user_id: str,
    ) -> list[TenantMembership]:
        statement: Select[TenantMembership] = self._scope(
            select(TenantMembership),
            TenantMembership.tenant_id,
        ).where(TenantMembership.user_id == user_id)

        result = await self._session.scalars(statement)

        return list(result.all())

    async def list_active_for_user(
        self,
        user_id: str,
    ) -> list[TenantMembership]:
        statement: Select[TenantMembership] = self._scope(
            select(TenantMembership),
            TenantMembership.tenant_id,
        ).where(
            TenantMembership.user_id == user_id,
            TenantMembership.active.is_(True),
        )

        result = await self._session.scalars(statement)

        return list(result.all())
