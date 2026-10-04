from __future__ import annotations

from uuid import UUID

import pytest

from app.authorization import (
    AuthorizationContext,
    AuthorizationDeniedError,
    ConversationAccessResource,
    ConversationActorContext,
    ConversationReassignmentTarget,
    Role,
    TenantIsolationError,
    can_reassign_conversation,
)

TENANT_A_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

TENANT_B_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")

SALES_GROUP_ID = UUID("11111111-1111-1111-1111-111111111111")

ACCOUNTING_GROUP_ID = UUID("22222222-2222-2222-2222-222222222222")

AHMED_EMPLOYEE_ID = UUID("33333333-3333-3333-3333-333333333333")

MOHAMED_EMPLOYEE_ID = UUID("44444444-4444-4444-4444-444444444444")


def make_conversation(
    *,
    tenant_id: UUID = TENANT_A_ID,
    group_id: UUID = SALES_GROUP_ID,
    responsible_employee_id: UUID | None = AHMED_EMPLOYEE_ID,
    is_queued: bool = False,
) -> ConversationAccessResource:
    return ConversationAccessResource(
        tenant_id=tenant_id,
        group_id=group_id,
        responsible_employee_id=responsible_employee_id,
        is_queued=is_queued,
    )


def make_target(
    *,
    tenant_id: UUID = TENANT_A_ID,
    employee_id: UUID = MOHAMED_EMPLOYEE_ID,
    member_group_ids: frozenset[UUID] | None = None,
) -> ConversationReassignmentTarget:
    if member_group_ids is None:
        member_group_ids = frozenset({SALES_GROUP_ID})

    return ConversationReassignmentTarget(
        tenant_id=tenant_id,
        employee_id=employee_id,
        member_group_ids=member_group_ids,
    )


def test_tenant_admin_can_reassign_to_valid_group_member() -> None:
    context = AuthorizationContext(
        actor_id="tenant-admin-123",
        role=Role.TENANT_ADMIN,
        tenant_id=TENANT_A_ID,
    )

    assert can_reassign_conversation(
        context,
        ConversationActorContext(),
        make_conversation(),
        make_target(),
    )


def test_tenant_admin_can_assign_unowned_conversation() -> None:
    context = AuthorizationContext(
        actor_id="tenant-admin-123",
        role=Role.TENANT_ADMIN,
        tenant_id=TENANT_A_ID,
    )

    conversation = make_conversation(
        responsible_employee_id=None,
        is_queued=True,
    )

    assert can_reassign_conversation(
        context,
        ConversationActorContext(),
        conversation,
        make_target(),
    )


def test_tenant_admin_cannot_reassign_to_employee_outside_group() -> None:
    context = AuthorizationContext(
        actor_id="tenant-admin-123",
        role=Role.TENANT_ADMIN,
        tenant_id=TENANT_A_ID,
    )

    target = make_target(
        member_group_ids=frozenset({ACCOUNTING_GROUP_ID}),
    )

    assert not can_reassign_conversation(
        context,
        ConversationActorContext(),
        make_conversation(),
        target,
    )


def test_target_from_foreign_tenant_is_rejected() -> None:
    context = AuthorizationContext(
        actor_id="tenant-admin-123",
        role=Role.TENANT_ADMIN,
        tenant_id=TENANT_A_ID,
    )

    target = make_target(
        tenant_id=TENANT_B_ID,
    )

    with pytest.raises(TenantIsolationError):
        can_reassign_conversation(
            context,
            ConversationActorContext(),
            make_conversation(),
            target,
        )


def test_reassigning_to_current_owner_is_rejected_as_no_op() -> None:
    context = AuthorizationContext(
        actor_id="tenant-admin-123",
        role=Role.TENANT_ADMIN,
        tenant_id=TENANT_A_ID,
    )

    target = make_target(
        employee_id=AHMED_EMPLOYEE_ID,
    )

    assert not can_reassign_conversation(
        context,
        ConversationActorContext(),
        make_conversation(
            responsible_employee_id=AHMED_EMPLOYEE_ID,
        ),
        target,
    )


def test_group_admin_can_reassign_in_administered_group() -> None:
    context = AuthorizationContext(
        actor_id="group-admin-123",
        role=Role.GROUP_ADMIN,
        tenant_id=TENANT_A_ID,
    )

    actor = ConversationActorContext(
        administered_group_ids=frozenset({SALES_GROUP_ID}),
    )

    assert can_reassign_conversation(
        context,
        actor,
        make_conversation(),
        make_target(),
    )


def test_group_admin_does_not_need_to_be_operational_group_member() -> None:
    context = AuthorizationContext(
        actor_id="group-admin-123",
        role=Role.GROUP_ADMIN,
        tenant_id=TENANT_A_ID,
    )

    actor = ConversationActorContext(
        member_group_ids=frozenset({ACCOUNTING_GROUP_ID}),
        administered_group_ids=frozenset({SALES_GROUP_ID}),
    )

    assert can_reassign_conversation(
        context,
        actor,
        make_conversation(),
        make_target(),
    )


def test_group_admin_cannot_reassign_outside_administered_groups() -> None:
    context = AuthorizationContext(
        actor_id="group-admin-123",
        role=Role.GROUP_ADMIN,
        tenant_id=TENANT_A_ID,
    )

    actor = ConversationActorContext(
        administered_group_ids=frozenset({ACCOUNTING_GROUP_ID}),
    )

    assert not can_reassign_conversation(
        context,
        actor,
        make_conversation(),
        make_target(),
    )


def test_group_admin_cannot_reassign_to_non_member_target() -> None:
    context = AuthorizationContext(
        actor_id="group-admin-123",
        role=Role.GROUP_ADMIN,
        tenant_id=TENANT_A_ID,
    )

    actor = ConversationActorContext(
        administered_group_ids=frozenset({SALES_GROUP_ID}),
    )

    target = make_target(
        member_group_ids=frozenset({ACCOUNTING_GROUP_ID}),
    )

    assert not can_reassign_conversation(
        context,
        actor,
        make_conversation(),
        target,
    )


def test_employee_cannot_reassign_conversation() -> None:
    context = AuthorizationContext(
        actor_id="employee-ahmed",
        role=Role.EMPLOYEE,
        tenant_id=TENANT_A_ID,
    )

    actor = ConversationActorContext(
        employee_id=AHMED_EMPLOYEE_ID,
        member_group_ids=frozenset({SALES_GROUP_ID}),
    )

    with pytest.raises(AuthorizationDeniedError):
        can_reassign_conversation(
            context,
            actor,
            make_conversation(),
            make_target(),
        )


def test_integration_cannot_reassign_conversation() -> None:
    context = AuthorizationContext(
        actor_id="integration-tenant-a",
        role=Role.INTEGRATION,
        tenant_id=TENANT_A_ID,
    )

    with pytest.raises(AuthorizationDeniedError):
        can_reassign_conversation(
            context,
            ConversationActorContext(),
            make_conversation(),
            make_target(),
        )


def test_platform_admin_has_no_implicit_reassign_permission() -> None:
    context = AuthorizationContext(
        actor_id="platform-admin-123",
        role=Role.PLATFORM_ADMIN,
        tenant_id=TENANT_A_ID,
    )

    with pytest.raises(AuthorizationDeniedError):
        can_reassign_conversation(
            context,
            ConversationActorContext(),
            make_conversation(),
            make_target(),
        )


def test_foreign_conversation_is_rejected_before_reassign_acl() -> None:
    context = AuthorizationContext(
        actor_id="tenant-admin-123",
        role=Role.TENANT_ADMIN,
        tenant_id=TENANT_A_ID,
    )

    with pytest.raises(TenantIsolationError):
        can_reassign_conversation(
            context,
            ConversationActorContext(),
            make_conversation(
                tenant_id=TENANT_B_ID,
            ),
            make_target(),
        )


def test_foreign_conversation_is_rejected_before_target_validation() -> None:
    context = AuthorizationContext(
        actor_id="group-admin-123",
        role=Role.GROUP_ADMIN,
        tenant_id=TENANT_A_ID,
    )

    actor = ConversationActorContext(
        administered_group_ids=frozenset(),
    )

    invalid_target = make_target(
        member_group_ids=frozenset(),
    )

    with pytest.raises(TenantIsolationError):
        can_reassign_conversation(
            context,
            actor,
            make_conversation(
                tenant_id=TENANT_B_ID,
            ),
            invalid_target,
        )
