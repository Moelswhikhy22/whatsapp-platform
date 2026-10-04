from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.authorization.roles import Role


@dataclass(frozen=True, slots=True, init=False)
class AuthorizationContext:
    """Trusted authorization state for the current actor.

    A human actor may have more than one role inside the active tenant.

    `actor_id` is the stable authenticated identity known to the
    application.

    `tenant_id` is None only for actors performing platform-level
    operations outside a tenant boundary.

    `role` remains supported temporarily for single-role callers while
    the existing resource policies are migrated to multi-role checks.
    """

    actor_id: str
    roles: frozenset[Role]
    tenant_id: UUID | None

    def __init__(
        self,
        actor_id: str,
        role: Role | None = None,
        tenant_id: UUID | None = None,
        *,
        roles: frozenset[Role] | None = None,
    ) -> None:
        if not actor_id.strip():
            raise ValueError("Authorization actor_id must not be empty.")

        if role is not None and roles is not None:
            raise ValueError("Provide either role or roles, not both.")

        if roles is not None:
            resolved_roles = roles
        elif role is not None:
            resolved_roles = frozenset({role})
        else:
            resolved_roles = frozenset()

        if not resolved_roles:
            raise ValueError("Authorization context must contain at least one role.")

        object.__setattr__(self, "actor_id", actor_id)
        object.__setattr__(self, "roles", resolved_roles)
        object.__setattr__(self, "tenant_id", tenant_id)

    @property
    def role(self) -> Role:
        """Return the role for legacy single-role policy code.

        Multi-role contexts must use `roles` or `has_role()` instead.
        This property intentionally fails closed rather than selecting
        one role arbitrarily.
        """

        if len(self.roles) != 1:
            raise ValueError(
                "Authorization context contains multiple roles; use roles or has_role()."
            )

        return next(iter(self.roles))

    def has_role(
        self,
        role: Role,
    ) -> bool:
        return role in self.roles
