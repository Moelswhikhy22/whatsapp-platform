from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.tenant import Tenant, TenantStatus
from app.db.models.tenant_domain import TenantDomain
from app.tenants.context import (
    TenantContext,
    TenantContextSource,
)


class TenantResolutionError(Exception):
    """Base error for tenant-resolution failures."""


class InvalidTenantHostnameError(TenantResolutionError):
    """Raised when a hostname cannot be normalized safely."""


class TenantNotFoundError(TenantResolutionError):
    """Raised when no active tenant domain matches the hostname."""


class TenantUnavailableError(TenantResolutionError):
    """Raised when a tenant exists but is not active."""

    def __init__(
        self,
        *,
        tenant_id: UUID,
        status: TenantStatus,
    ) -> None:
        self.tenant_id = tenant_id
        self.status = status

        super().__init__("Tenant is not active.")


class TenantResolutionConflictError(TenantResolutionError):
    """Raised when hostname resolution is unexpectedly ambiguous."""


def normalize_tenant_hostname(hostname: str) -> str:
    value = hostname.strip().rstrip(".")

    if not value:
        raise InvalidTenantHostnameError("Tenant hostname is empty.")

    if "/" in value or ":" in value:
        raise InvalidTenantHostnameError("Expected a hostname without scheme, path, or port.")

    try:
        normalized = value.encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise InvalidTenantHostnameError("Tenant hostname is invalid.") from exc

    if len(normalized) > 253:
        raise InvalidTenantHostnameError("Tenant hostname is too long.")

    return normalized


class TenantResolver:
    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self._session = session

    async def resolve_by_hostname(
        self,
        hostname: str,
    ) -> Tenant:
        normalized_hostname = normalize_tenant_hostname(hostname)

        statement = (
            select(Tenant)
            .join(
                TenantDomain,
                TenantDomain.tenant_id == Tenant.id,
            )
            .where(
                func.lower(TenantDomain.hostname) == normalized_hostname,
                TenantDomain.active.is_(True),
            )
            .limit(2)
        )

        result = await self._session.scalars(statement)

        tenants = list(result.all())

        if not tenants:
            raise TenantNotFoundError("No active tenant domain matches the hostname.")

        if len(tenants) > 1:
            raise TenantResolutionConflictError("Hostname resolves to multiple tenants.")

        tenant = tenants[0]

        if tenant.status is not TenantStatus.ACTIVE:
            raise TenantUnavailableError(
                tenant_id=tenant.id,
                status=tenant.status,
            )

        return tenant

    async def resolve_context_by_hostname(
        self,
        hostname: str,
    ) -> TenantContext:
        tenant = await self.resolve_by_hostname(hostname)

        return TenantContext.from_tenant(
            tenant,
            source=TenantContextSource.HOSTNAME,
        )
