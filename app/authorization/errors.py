from __future__ import annotations

from app.authorization.permissions import Permission


class AuthorizationDeniedError(PermissionError):
    """Raised when an authenticated actor lacks a required permission."""

    def __init__(
        self,
        permission: Permission,
    ) -> None:
        super().__init__("Authorization denied.")
        self.permission = permission
