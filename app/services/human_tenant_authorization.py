from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.id_token import HumanPrincipal
from app.auth.roles import HUMAN_ROLES
from app.authorization.context import AuthorizationContext
from app.authorization.roles import Role
from app.db.models.tenant_membership import TenantMembership
from app.tenants.context import TenantContext


class HumanTenantAuthorizationError(RuntimeError):
    """Base error for resolving human tenant authorization."""


class HumanTenantMembershipNotFoundError(HumanTenantAuthorizationError):
    """Raised when the user has no active membership in the tenant."""


class InvalidHumanTenantRoleError(HumanTenantAuthorizationError):
    """Raised when an active membership contains an invalid human role."""


@dataclass(
    frozen=True,
    slots=True,
)
class HumanTenantAuthorization:
    context: AuthorizationContext


class HumanTenantAuthorizationResolver:
    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self._session = session

    async def resolve(
        self,
        *,
        principal: HumanPrincipal,
        tenant_context: TenantContext,
    ) -> HumanTenantAuthorization:
        statement = select(
            TenantMembership.role_id,
        ).where(
            TenantMembership.tenant_id == tenant_context.tenant_id,
            TenantMembership.user_id == principal.subject,
            TenantMembership.active.is_(True),
        )

        result = await self._session.scalars(statement)

        role_ids = list(result.all())

        if not role_ids:
            raise HumanTenantMembershipNotFoundError(
                "The authenticated user has no active membership in this tenant."
            )

        roles: set[Role] = set()

        for role_id in role_ids:
            try:
                role = Role(role_id)
            except ValueError as exc:
                raise InvalidHumanTenantRoleError(f"Unknown tenant role: {role_id}") from exc

            if role not in HUMAN_ROLES:
                raise InvalidHumanTenantRoleError(
                    "Machine roles cannot be used by human tenant sessions."
                )

            roles.add(role)

        context = AuthorizationContext(
            actor_id=principal.subject,
            tenant_id=tenant_context.tenant_id,
            roles=frozenset(roles),
        )

        return HumanTenantAuthorization(
            context=context,
        )
