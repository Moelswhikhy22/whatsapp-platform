from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from app.authorization.context import AuthorizationContext
from app.authorization.permissions import Permission
from app.authorization.policy import require_tenant_permission
from app.authorization.roles import Role
from app.authorization.tenant_isolation import ensure_same_tenant


@dataclass(frozen=True, slots=True)
class ConversationAccessResource:
    """Authorization-relevant snapshot of a conversation.

    This object is deliberately independent from SQLAlchemy so
    authorization policies can be tested without database access.
    """

    tenant_id: UUID
    group_id: UUID
    responsible_employee_id: UUID | None
    is_queued: bool


@dataclass(frozen=True, slots=True)
class ConversationActorContext:
    """Actor relationships relevant to conversation authorization."""

    employee_id: UUID | None = None
    member_group_ids: frozenset[UUID] = field(default_factory=frozenset)
    administered_group_ids: frozenset[UUID] = field(default_factory=frozenset)


@dataclass(frozen=True, slots=True)
class ConversationReassignmentTarget:
    """Authorization-relevant snapshot of a reassignment target."""

    tenant_id: UUID
    employee_id: UUID
    member_group_ids: frozenset[UUID] = field(default_factory=frozenset)


@dataclass(frozen=True, slots=True)
class ConversationTransferDestination:
    """Authorization-relevant snapshot of a transfer destination."""

    tenant_id: UUID
    group_id: UUID


@dataclass(frozen=True, slots=True)
class ConversationVisibilityPolicy:
    """Group-level policy affecting conversation visibility."""

    team_read_after_claim: bool = False


@dataclass(frozen=True, slots=True)
class ConversationSendPolicy:
    """Group-level policy affecting outbound conversation sending.

    By default, a normal employee may send only when they are the
    responsible employee. Explicit group policy may allow another
    member of the same group to send without taking ownership.
    """

    allow_non_owner_employee_send: bool = False


def can_view_conversation(
    context: AuthorizationContext,
    actor: ConversationActorContext,
    conversation: ConversationAccessResource,
    policy: ConversationVisibilityPolicy,
) -> bool:
    """Return whether the actor may view a specific conversation.

    Tenant isolation and RBAC are enforced before relationship-based
    conversation ACL rules are evaluated.
    """

    require_tenant_permission(
        context,
        conversation.tenant_id,
        Permission.CONVERSATION_READ,
    )

    if context.role is Role.TENANT_ADMIN:
        return True

    if context.role is Role.GROUP_ADMIN:
        return conversation.group_id in actor.administered_group_ids

    if context.role is Role.EMPLOYEE:
        return _employee_can_view_conversation(
            actor,
            conversation,
            policy,
        )

    return context.role is Role.INTEGRATION


def can_claim_conversation(
    context: AuthorizationContext,
    actor: ConversationActorContext,
    conversation: ConversationAccessResource,
) -> bool:
    """Return whether the actor may self-claim a conversation.

    Claim is always a self-claim operation. The actor must have an
    employee identity because a successful claim makes that employee
    the responsible employee.

    This function performs authorization and claim precondition checks.
    It does not provide concurrency guarantees. The eventual database
    claim operation must still be atomic.
    """

    require_tenant_permission(
        context,
        conversation.tenant_id,
        Permission.CONVERSATION_CLAIM,
    )

    if not _is_claimable(conversation):
        return False

    if actor.employee_id is None:
        return False

    if context.role is Role.EMPLOYEE:
        return conversation.group_id in actor.member_group_ids

    if context.role is Role.GROUP_ADMIN:
        return (
            conversation.group_id in actor.member_group_ids
            and conversation.group_id in actor.administered_group_ids
        )

    if context.role is Role.TENANT_ADMIN:
        return conversation.group_id in actor.member_group_ids

    return False


def can_send_message(
    context: AuthorizationContext,
    actor: ConversationActorContext,
    conversation: ConversationAccessResource,
    policy: ConversationSendPolicy,
) -> bool:
    """Return whether the actor may send in a specific conversation.

    Tenant isolation and message:send RBAC are enforced before the
    conversation-level ACL is evaluated.

    Human actors normally send only after a conversation has an owner.
    Employees must be members of the conversation group and, by
    default, must be the responsible employee.

    Integrations are evaluated here only as machine identities. An
    integration representing a human employee, such as Odoo, must also
    pass that represented employee's authorization in the integration
    layer.
    """

    require_tenant_permission(
        context,
        conversation.tenant_id,
        Permission.MESSAGE_SEND,
    )

    if context.role is Role.INTEGRATION:
        return True

    if conversation.responsible_employee_id is None:
        return False

    if context.role is Role.TENANT_ADMIN:
        return True

    if context.role is Role.GROUP_ADMIN:
        return conversation.group_id in actor.administered_group_ids

    if context.role is Role.EMPLOYEE:
        return _employee_can_send_message(
            actor,
            conversation,
            policy,
        )

    return False


def can_reassign_conversation(
    context: AuthorizationContext,
    actor: ConversationActorContext,
    conversation: ConversationAccessResource,
    target: ConversationReassignmentTarget,
) -> bool:
    """Return whether the actor may assign the conversation to target.

    Reassignment changes the responsible employee only. It does not
    transfer the conversation to another group.

    The target employee must belong to the current conversation group.
    Tenant isolation is enforced for both the conversation and target
    before relationship-based ACL rules are evaluated.

    A target equal to the current responsible employee is rejected as
    a no-op.
    """

    require_tenant_permission(
        context,
        conversation.tenant_id,
        Permission.CONVERSATION_REASSIGN,
    )

    ensure_same_tenant(
        context.tenant_id,
        target.tenant_id,
    )

    if conversation.group_id not in target.member_group_ids:
        return False

    if conversation.responsible_employee_id == target.employee_id:
        return False

    if context.role is Role.TENANT_ADMIN:
        return True

    if context.role is Role.GROUP_ADMIN:
        return conversation.group_id in actor.administered_group_ids

    return False


def can_transfer_conversation(
    context: AuthorizationContext,
    actor: ConversationActorContext,
    conversation: ConversationAccessResource,
    destination: ConversationTransferDestination,
) -> bool:
    """Return whether the actor may transfer a conversation.

    Transfer changes the conversation group. Both the conversation and
    destination group must belong to the active tenant.

    Tenant Admins may transfer conversations anywhere inside their
    tenant. Group Admins may transfer conversations that belong to a
    group they administer.

    Destination authorization does not require the Group Admin to
    administer the destination group. The caller's authority is over
    the source conversation. Destination existence and operational
    validity remain repository/service-layer concerns.
    """

    require_tenant_permission(
        context,
        conversation.tenant_id,
        Permission.CONVERSATION_TRANSFER,
    )

    ensure_same_tenant(
        context.tenant_id,
        destination.tenant_id,
    )

    if destination.group_id == conversation.group_id:
        return False

    if context.role is Role.TENANT_ADMIN:
        return True

    if context.role is Role.GROUP_ADMIN:
        return conversation.group_id in actor.administered_group_ids

    return False


def _employee_can_view_conversation(
    actor: ConversationActorContext,
    conversation: ConversationAccessResource,
    policy: ConversationVisibilityPolicy,
) -> bool:
    employee_id = actor.employee_id

    if employee_id is None:
        return False

    if conversation.group_id not in actor.member_group_ids:
        return False

    if conversation.responsible_employee_id == employee_id:
        return True

    if conversation.is_queued and conversation.responsible_employee_id is None:
        return True

    return conversation.responsible_employee_id is not None and policy.team_read_after_claim


def _employee_can_send_message(
    actor: ConversationActorContext,
    conversation: ConversationAccessResource,
    policy: ConversationSendPolicy,
) -> bool:
    employee_id = actor.employee_id

    if employee_id is None:
        return False

    if conversation.group_id not in actor.member_group_ids:
        return False

    if conversation.responsible_employee_id == employee_id:
        return True

    return policy.allow_non_owner_employee_send


def _is_claimable(
    conversation: ConversationAccessResource,
) -> bool:
    return conversation.is_queued and conversation.responsible_employee_id is None
