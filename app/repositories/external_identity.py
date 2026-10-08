from __future__ import annotations

from sqlalchemy import Select, and_, select

from app.db.models.employee import Employee
from app.db.models.external_identity import ExternalIdentity
from app.repositories.base import TenantScopedRepository


class ExternalIdentityRepository(TenantScopedRepository):
    async def get_active_employee_by_provider_user(
        self,
        *,
        provider: str,
        external_user_id: str,
    ) -> Employee | None:
        statement: Select[Employee] = self._scope(
            select(Employee)
            .join(
                ExternalIdentity,
                and_(
                    ExternalIdentity.tenant_id == Employee.tenant_id,
                    ExternalIdentity.employee_id == Employee.id,
                ),
            )
            .where(
                ExternalIdentity.provider == provider,
                ExternalIdentity.external_user_id == external_user_id,
                Employee.active.is_(True),
            ),
            Employee.tenant_id,
        )

        result = await self._session.scalars(statement)

        return result.first()
