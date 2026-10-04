from __future__ import annotations

from uuid import UUID


class TenantIsolationError(LookupError):
    """Raised when access crosses or lacks a trusted tenant boundary."""


def ensure_same_tenant(
    current_tenant_id: UUID | None,
    resource_tenant_id: UUID,
) -> None:
    """Ensure a tenant-owned resource belongs to the active tenant.

    The check intentionally does not know anything about roles or
    permissions. Tenant isolation must happen before RBAC and ACL.

    A missing current tenant fails closed.
    """

    if current_tenant_id is None:
        raise TenantIsolationError("A trusted tenant context is required.")

    if current_tenant_id != resource_tenant_id:
        raise TenantIsolationError("Resource is outside the active tenant boundary.")


def is_same_tenant(
    current_tenant_id: UUID | None,
    resource_tenant_id: UUID,
) -> bool:
    """Return whether a resource belongs to the active tenant."""

    return current_tenant_id is not None and current_tenant_id == resource_tenant_id
