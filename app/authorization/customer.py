from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from app.authorization.context import AuthorizationContext
from app.authorization.permissions import Permission
from app.authorization.policy import require_tenant_permission
from app.authorization.roles import Role


@dataclass(frozen=True, slots=True)
class CustomerAccessResource:
    """Authorization-relevant snapshot of a customer company.

    A customer may be associated with multiple groups inside the same
    tenant. Group relationships are used for resource-level ACL checks.

    The actual CustomerCompany and group-association database models
    are intentionally not required by this authorization policy.
    """

    tenant_id: UUID
    group_ids: frozenset[UUID] = field(default_factory=frozenset)


@dataclass(frozen=True, slots=True)
class CustomerActorContext:
    """Actor relationships relevant to customer authorization."""

    administered_group_ids: frozenset[UUID] = field(default_factory=frozenset)


def can_modify_customer(
    context: AuthorizationContext,
    actor: CustomerActorContext,
    customer: CustomerAccessResource,
) -> bool:
    """Return whether the actor may modify a specific customer.

    Tenant isolation and customer:update RBAC are enforced before
    relationship-based customer ACL rules.

    Tenant Admins may modify any customer inside their tenant.

    Group Admins may modify a customer only when at least one customer
    group is administered by that Group Admin.

    Customer records without group associations are therefore not
    modifiable by Group Admins.
    """

    require_tenant_permission(
        context,
        customer.tenant_id,
        Permission.CUSTOMER_UPDATE,
    )

    if context.role is Role.TENANT_ADMIN:
        return True

    if context.role is Role.GROUP_ADMIN:
        return bool(customer.group_ids & actor.administered_group_ids)

    return False
