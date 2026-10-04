from __future__ import annotations

from app.auth.exceptions import PermissionDeniedError
from app.auth.permissions import Permission
from app.auth.principals import Principal


def has_permission(
    principal: Principal,
    permission: Permission,
) -> bool:
    """
    Return whether the principal has the requested RBAC permission.

    This function performs RBAC evaluation only.

    It does not evaluate:
    - tenant isolation
    - group membership
    - conversation ownership
    - resource-level ACL
    """

    return principal.has_permission(permission)


def require_permission(
    principal: Principal,
    permission: Permission,
) -> None:
    """
    Require a principal to have an RBAC permission.

    Raises PermissionDeniedError when the permission is missing.
    """

    if not has_permission(principal, permission):
        raise PermissionDeniedError(permission)
