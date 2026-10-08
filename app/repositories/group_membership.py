from __future__ import annotations

from uuid import UUID

from sqlalchemy import Select, select

from app.db.models.group_membership import GroupMembership
from app.repositories.base import TenantScopedRepository


class GroupMembershipRepository(TenantScopedRepository):
    async def list_active_for_employee(
        self,
        employee_id: UUID,
    ) -> list[GroupMembership]:
        statement: Select[GroupMembership] = self._scope(
            select(GroupMembership),
            GroupMembership.tenant_id,
        ).where(
            GroupMembership.employee_id == employee_id,
            GroupMembership.active.is_(True),
        )

        result = await self._session.scalars(statement)

        return list(result.all())
