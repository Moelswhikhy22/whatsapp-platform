from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from app.db.models.tenant import Tenant, TenantStatus


class InvalidTenantContextError(ValueError):
    """Raised when a tenant cannot produce a valid request context."""


class TenantContextSource(StrEnum):
    HOSTNAME = "hostname"
    AUTHENTICATED_SESSION = "authenticated_session"
    INTEGRATION = "integration"
    PROVIDER_IDENTITY = "provider_identity"


@dataclass(frozen=True, slots=True)
class TenantContext:
    tenant_id: UUID
    slug: str
    source: TenantContextSource

    def __post_init__(self) -> None:
        if self.tenant_id.int == 0:
            raise InvalidTenantContextError("Tenant ID cannot be the nil UUID.")

        if not self.slug.strip():
            raise InvalidTenantContextError("Tenant slug cannot be empty.")

    @classmethod
    def from_tenant(
        cls,
        tenant: Tenant,
        *,
        source: TenantContextSource,
    ) -> TenantContext:
        if tenant.status is not TenantStatus.ACTIVE:
            raise InvalidTenantContextError(
                "Tenant context can only be created for an active tenant."
            )

        return cls(
            tenant_id=tenant.id,
            slug=tenant.slug.strip(),
            source=source,
        )
