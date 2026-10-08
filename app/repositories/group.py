from __future__ import annotations

from uuid import UUID

from sqlalchemy import Select, and_, select

from app.db.models.employee import Employee
from app.db.models.group import Group
from app.db.models.group_membership import GroupMembership
from app.repositories.base import TenantScopedRepository


class GroupRepository(TenantScopedRepository):
    async def get_by_id(
        self,
        group_id: UUID,
    ) -> Group | None:
        statement: Select[Group] = self._scope(
            select(Group),
            Group.tenant_id,
        ).where(
            Group.id == group_id,
        )

        result = await self._session.scalars(statement)

        return result.first()

    async def list_active_admin_employee_ids(
        self,
        group_id: UUID,
    ) -> list[UUID]:
        statement = (
            self._scope(
                select(Employee.id),
                Employee.tenant_id,
            )
            .join(
                GroupMembership,
                and_(
                    GroupMembership.tenant_id == Employee.tenant_id,
                    GroupMembership.employee_id == Employee.id,
                ),
            )
            .where(
                GroupMembership.group_id == group_id,
                GroupMembership.active.is_(True),
                GroupMembership.is_admin.is_(True),
                Employee.active.is_(True),
            )
            .order_by(Employee.id.asc())
        )

        result = await self._session.scalars(statement)

        return list(result.all())
