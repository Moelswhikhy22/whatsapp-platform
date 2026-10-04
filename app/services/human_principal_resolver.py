from __future__ import annotations

from app.auth.principals import HumanPrincipal
from app.authorization.roles import Role
from app.repositories.tenant_membership import TenantMembershipRepository


class HumanTenantMembershipDeniedError(PermissionError):
    """Raised when a human has no valid active membership in the tenant."""


TENANT_HUMAN_ROLES: frozenset[Role] = frozenset(
    {
        Role.TENANT_ADMIN,
        Role.GROUP_ADMIN,
        Role.EMPLOYEE,
    }
)


class HumanPrincipalResolver:
    def __init__(
        self,
        membership_repository: TenantMembershipRepository,
    ) -> None:
        self._membership_repository = membership_repository

    async def resolve(
        self,
        *,
        subject: str,
    ) -> HumanPrincipal:
        if not subject.strip():
            raise ValueError("subject must not be empty")

        memberships = await self._membership_repository.list_active_for_user(
            subject,
        )

        if not memberships:
            raise HumanTenantMembershipDeniedError("No active tenant membership.")

        roles: set[Role] = set()

        for membership in memberships:
            try:
                role = Role(membership.role_id)
            except ValueError as exc:
                raise HumanTenantMembershipDeniedError("Invalid tenant membership role.") from exc

            if role not in TENANT_HUMAN_ROLES:
                raise HumanTenantMembershipDeniedError("Invalid tenant membership role.")

            roles.add(role)

        if not roles:
            raise HumanTenantMembershipDeniedError("No valid tenant role.")

        return HumanPrincipal(
            subject=subject,
            roles=frozenset(roles),
        )
