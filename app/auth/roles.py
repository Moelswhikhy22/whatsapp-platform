from __future__ import annotations

from app.authorization.roles import Role

HUMAN_ROLES: frozenset[Role] = frozenset(
    {
        Role.PLATFORM_ADMIN,
        Role.TENANT_ADMIN,
        Role.GROUP_ADMIN,
        Role.EMPLOYEE,
    }
)

MACHINE_ROLES: frozenset[Role] = frozenset(
    {
        Role.INTEGRATION,
    }
)


__all__ = [
    "HUMAN_ROLES",
    "MACHINE_ROLES",
    "Role",
]
