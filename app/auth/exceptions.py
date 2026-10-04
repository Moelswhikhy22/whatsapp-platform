from __future__ import annotations

from app.auth.permissions import Permission


class AuthorizationError(Exception):
    """Base exception for authorization failures."""

    code = "AUTHORIZATION_DENIED"


class PermissionDeniedError(AuthorizationError):
    """Raised when a principal lacks a required RBAC permission."""

    code = "PERMISSION_DENIED"

    def __init__(self, permission: Permission) -> None:
        self.permission = permission

        super().__init__(f"Missing required permission: {permission.value}")


class TenantIsolationError(AuthorizationError):
    """
    Raised when an operation attempts to cross
    the active tenant boundary.
    """

    code = "TENANT_ISOLATION_VIOLATION"

    def __init__(self) -> None:
        super().__init__("Resource is outside the active tenant context")
