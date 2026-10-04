from __future__ import annotations

from uuid import UUID

from sqlalchemy import Select, func, select

from app.db.models.tenant_domain import TenantDomain
from app.repositories.base import TenantScopedRepository
from app.services.tenant_resolver import normalize_tenant_hostname


class TenantDomainRepository(TenantScopedRepository):
    async def get_by_id(
        self,
        domain_id: UUID,
    ) -> TenantDomain | None:
        statement: Select[TenantDomain] = self._scope(
            select(TenantDomain),
            TenantDomain.tenant_id,
        ).where(TenantDomain.id == domain_id)

        result = await self._session.scalars(statement)

        return result.first()

    async def get_by_hostname(
        self,
        hostname: str,
    ) -> TenantDomain | None:
        normalized_hostname = normalize_tenant_hostname(hostname)

        statement: Select[TenantDomain] = self._scope(
            select(TenantDomain),
            TenantDomain.tenant_id,
        ).where(func.lower(TenantDomain.hostname) == normalized_hostname)

        result = await self._session.scalars(statement)

        return result.first()

    async def list_all(
        self,
    ) -> list[TenantDomain]:
        statement: Select[TenantDomain] = self._scope(
            select(TenantDomain),
            TenantDomain.tenant_id,
        ).order_by(TenantDomain.hostname)

        result = await self._session.scalars(statement)

        return list(result.all())
