from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from app.auth.permissions import Permission
from app.auth.role_permissions import permissions_for_role
from app.auth.roles import Role


class ActorType(StrEnum):
    HUMAN = "human"
    INTEGRATION = "integration"


@dataclass(frozen=True, slots=True)
class HumanPrincipal:
    """
    Authenticated human actor.

    `subject` is the identity-provider subject, for example the Keycloak
    `sub` claim.

    The roles stored here are the roles already resolved for the current
    authorization context. Tenant membership resolution will be added
    separately.

    A human principal must never contain the Integration role.
    """

    subject: str
    roles: frozenset[Role]
    employee_id: UUID | None = None

    def __post_init__(self) -> None:
        if not self.subject.strip():
            raise ValueError("human principal subject must not be empty")

        if not self.roles:
            raise ValueError("human principal must have at least one role")

        if Role.INTEGRATION in self.roles:
            raise ValueError("integration role cannot be assigned to HumanPrincipal")

    @property
    def actor_type(self) -> ActorType:
        return ActorType.HUMAN

    @property
    def permissions(self) -> frozenset[Permission]:
        granted: set[Permission] = set()

        for role in self.roles:
            granted.update(permissions_for_role(role))

        return frozenset(granted)

    def has_permission(self, permission: Permission) -> bool:
        return permission in self.permissions


@dataclass(frozen=True, slots=True)
class IntegrationPrincipal:
    """
    Authenticated machine/service identity.

    An IntegrationPrincipal represents the calling service itself, such as
    an Odoo connector.

    It does NOT automatically represent a human employee.

    `tenant_id` is mandatory because integrations in this platform are
    tenant-bound.

    `permissions` may be narrower than the general Integration role
    permission set, but it may never exceed it.
    """

    integration_id: UUID
    tenant_id: UUID
    client_id: str
    provider: str
    permissions: frozenset[Permission]

    def __post_init__(self) -> None:
        if not self.client_id.strip():
            raise ValueError("integration client_id must not be empty")

        if not self.provider.strip():
            raise ValueError("integration provider must not be empty")

        allowed_permissions = permissions_for_role(Role.INTEGRATION)

        invalid_permissions = self.permissions - allowed_permissions

        if invalid_permissions:
            invalid_values = ", ".join(
                sorted(permission.value for permission in invalid_permissions)
            )

            raise ValueError(
                "integration principal contains permissions not allowed "
                f"for Integration role: {invalid_values}"
            )

    @property
    def actor_type(self) -> ActorType:
        return ActorType.INTEGRATION

    @property
    def role(self) -> Role:
        return Role.INTEGRATION

    def has_permission(self, permission: Permission) -> bool:
        return permission in self.permissions


type Principal = HumanPrincipal | IntegrationPrincipal
