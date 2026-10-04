from __future__ import annotations

from uuid import UUID

from app.authorization.context import AuthorizationContext
from app.authorization.errors import AuthorizationDeniedError
from app.authorization.permissions import Permission
from app.authorization.role_permissions import (
    role_has_permission,
)
from app.authorization.tenant_isolation import (
    ensure_same_tenant,
)


def has_permission(
    context: AuthorizationContext,
    permission: Permission,
) -> bool:
    """Return whether any of the actor's roles grants a permission."""

    return any(
        role_has_permission(
            role,
            permission,
        )
        for role in context.roles
    )


def require_permission(
    context: AuthorizationContext,
    permission: Permission,
) -> None:
    """Require an RBAC permission for the current actor.

    This function performs RBAC only. It intentionally does not perform
    tenant or resource ACL checks.
    """

    if not has_permission(
        context,
        permission,
    ):
        raise AuthorizationDeniedError(permission)


def require_tenant_permission(
    context: AuthorizationContext,
    resource_tenant_id: UUID,
    permission: Permission,
) -> None:
    """Require tenant isolation before evaluating an RBAC permission.

    Tenant isolation is intentionally evaluated first so that a
    cross-tenant resource cannot become visible merely because the
    actor's role contains the requested permission.
    """

    ensure_same_tenant(
        context.tenant_id,
        resource_tenant_id,
    )

    require_permission(
        context,
        permission,
    )
