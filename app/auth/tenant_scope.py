from __future__ import annotations

from uuid import UUID

from app.auth.exceptions import TenantIsolationError
from app.auth.principals import IntegrationPrincipal
from app.tenants.context import TenantContext


def require_resource_tenant(
    tenant_context: TenantContext,
    resource_tenant_id: UUID,
) -> None:
    """
    Require the resource to belong to the active tenant.
    """

    if resource_tenant_id != tenant_context.tenant_id:
        raise TenantIsolationError


def require_integration_tenant(
    principal: IntegrationPrincipal,
    tenant_context: TenantContext,
) -> None:
    """
    Require the tenant-bound integration to match
    the active tenant context.
    """

    if principal.tenant_id != tenant_context.tenant_id:
        raise TenantIsolationError
