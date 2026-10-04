from __future__ import annotations

from uuid import UUID

import pytest

from app.authorization import (
    AuthorizationContext,
    AuthorizationDeniedError,
    ConversationAccessResource,
    ConversationActorContext,
    Role,
    TenantIsolationError,
    can_claim_conversation,
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
    responsible_employee_id: UUID | None = None,
    is_queued: bool = True,
) -> ConversationAccessResource:
    return ConversationAccessResource(
        tenant_id=tenant_id,
        group_id=group_id,
        responsible_employee_id=responsible_employee_id,
        is_queued=is_queued,
    )


def test_employee_can_self_claim_queued_conversation_in_own_group() -> None:
    context = AuthorizationContext(
        actor_id="employee-ahmed",
        role=Role.EMPLOYEE,
        tenant_id=TENANT_A_ID,
    )

    actor = ConversationActorContext(
        employee_id=AHMED_EMPLOYEE_ID,
        member_group_ids=frozenset({SALES_GROUP_ID}),
    )

    assert can_claim_conversation(
        context,
        actor,
        make_conversation(),
    )


def test_employee_cannot_claim_conversation_outside_own_groups() -> None:
    context = AuthorizationContext(
        actor_id="employee-ahmed",
        role=Role.EMPLOYEE,
        tenant_id=TENANT_A_ID,
    )

    actor = ConversationActorContext(
        employee_id=AHMED_EMPLOYEE_ID,
        member_group_ids=frozenset({ACCOUNTING_GROUP_ID}),
    )

    assert not can_claim_conversation(
        context,
        actor,
        make_conversation(),
    )


def test_employee_without_employee_identity_cannot_claim() -> None:
    context = AuthorizationContext(
        actor_id="employee-without-mapping",
        role=Role.EMPLOYEE,
        tenant_id=TENANT_A_ID,
    )

    actor = ConversationActorContext(
        member_group_ids=frozenset({SALES_GROUP_ID}),
    )

    assert not can_claim_conversation(
        context,
        actor,
        make_conversation(),
    )


def test_employee_cannot_claim_already_claimed_conversation() -> None:
    context = AuthorizationContext(
        actor_id="employee-ahmed",
        role=Role.EMPLOYEE,
        tenant_id=TENANT_A_ID,
    )

    actor = ConversationActorContext(
        employee_id=AHMED_EMPLOYEE_ID,
        member_group_ids=frozenset({SALES_GROUP_ID}),
    )

    conversation = make_conversation(
        responsible_employee_id=MOHAMED_EMPLOYEE_ID,
        is_queued=False,
    )

    assert not can_claim_conversation(
        context,
        actor,
        conversation,
    )


def test_employee_cannot_claim_owned_conversation_even_if_marked_queued() -> None:
    context = AuthorizationContext(
        actor_id="employee-ahmed",
        role=Role.EMPLOYEE,
        tenant_id=TENANT_A_ID,
    )

    actor = ConversationActorContext(
        employee_id=AHMED_EMPLOYEE_ID,
        member_group_ids=frozenset({SALES_GROUP_ID}),
    )

    conversation = make_conversation(
        responsible_employee_id=MOHAMED_EMPLOYEE_ID,
        is_queued=True,
    )

    assert not can_claim_conversation(
        context,
        actor,
        conversation,
    )


def test_employee_cannot_claim_unowned_non_queued_conversation() -> None:
    context = AuthorizationContext(
        actor_id="employee-ahmed",
        role=Role.EMPLOYEE,
        tenant_id=TENANT_A_ID,
    )

    actor = ConversationActorContext(
        employee_id=AHMED_EMPLOYEE_ID,
        member_group_ids=frozenset({SALES_GROUP_ID}),
    )

    conversation = make_conversation(
        responsible_employee_id=None,
        is_queued=False,
    )

    assert not can_claim_conversation(
        context,
        actor,
        conversation,
    )


def test_group_admin_can_self_claim_when_member_and_admin_of_group() -> None:
    context = AuthorizationContext(
        actor_id="group-admin-ahmed",
        role=Role.GROUP_ADMIN,
        tenant_id=TENANT_A_ID,
    )

    actor = ConversationActorContext(
        employee_id=AHMED_EMPLOYEE_ID,
        member_group_ids=frozenset({SALES_GROUP_ID}),
        administered_group_ids=frozenset({SALES_GROUP_ID}),
    )

    assert can_claim_conversation(
        context,
        actor,
        make_conversation(),
    )


def test_group_admin_cannot_claim_when_admin_but_not_member() -> None:
    context = AuthorizationContext(
        actor_id="group-admin-ahmed",
        role=Role.GROUP_ADMIN,
        tenant_id=TENANT_A_ID,
    )

    actor = ConversationActorContext(
        employee_id=AHMED_EMPLOYEE_ID,
        member_group_ids=frozenset({ACCOUNTING_GROUP_ID}),
        administered_group_ids=frozenset({SALES_GROUP_ID}),
    )

    assert not can_claim_conversation(
        context,
        actor,
        make_conversation(),
    )


def test_group_admin_cannot_claim_when_member_but_not_admin_of_group() -> None:
    context = AuthorizationContext(
        actor_id="group-admin-ahmed",
        role=Role.GROUP_ADMIN,
        tenant_id=TENANT_A_ID,
    )

    actor = ConversationActorContext(
        employee_id=AHMED_EMPLOYEE_ID,
        member_group_ids=frozenset({SALES_GROUP_ID}),
        administered_group_ids=frozenset({ACCOUNTING_GROUP_ID}),
    )

    assert not can_claim_conversation(
        context,
        actor,
        make_conversation(),
    )


def test_tenant_admin_can_self_claim_when_member_of_group() -> None:
    context = AuthorizationContext(
        actor_id="tenant-admin-ahmed",
        role=Role.TENANT_ADMIN,
        tenant_id=TENANT_A_ID,
    )

    actor = ConversationActorContext(
        employee_id=AHMED_EMPLOYEE_ID,
        member_group_ids=frozenset({SALES_GROUP_ID}),
    )

    assert can_claim_conversation(
        context,
        actor,
        make_conversation(),
    )


def test_tenant_admin_cannot_self_claim_when_not_group_member() -> None:
    context = AuthorizationContext(
        actor_id="tenant-admin-ahmed",
        role=Role.TENANT_ADMIN,
        tenant_id=TENANT_A_ID,
    )

    actor = ConversationActorContext(
        employee_id=AHMED_EMPLOYEE_ID,
        member_group_ids=frozenset({ACCOUNTING_GROUP_ID}),
    )

    assert not can_claim_conversation(
        context,
        actor,
        make_conversation(),
    )


def test_tenant_admin_without_employee_identity_cannot_claim() -> None:
    context = AuthorizationContext(
        actor_id="tenant-admin-123",
        role=Role.TENANT_ADMIN,
        tenant_id=TENANT_A_ID,
    )

    actor = ConversationActorContext(
        member_group_ids=frozenset({SALES_GROUP_ID}),
    )

    assert not can_claim_conversation(
        context,
        actor,
        make_conversation(),
    )


def test_integration_cannot_claim_conversation() -> None:
    context = AuthorizationContext(
        actor_id="odoo-tenant-a",
        role=Role.INTEGRATION,
        tenant_id=TENANT_A_ID,
    )

    with pytest.raises(AuthorizationDeniedError):
        can_claim_conversation(
            context,
            ConversationActorContext(),
            make_conversation(),
        )


def test_platform_admin_cannot_claim_conversation() -> None:
    context = AuthorizationContext(
        actor_id="platform-admin-123",
        role=Role.PLATFORM_ADMIN,
        tenant_id=TENANT_A_ID,
    )

    with pytest.raises(AuthorizationDeniedError):
        can_claim_conversation(
            context,
            ConversationActorContext(
                employee_id=AHMED_EMPLOYEE_ID,
                member_group_ids=frozenset({SALES_GROUP_ID}),
            ),
            make_conversation(),
        )


def test_foreign_tenant_is_rejected_before_claim_acl() -> None:
    context = AuthorizationContext(
        actor_id="employee-ahmed",
        role=Role.EMPLOYEE,
        tenant_id=TENANT_A_ID,
    )

    actor = ConversationActorContext(
        employee_id=AHMED_EMPLOYEE_ID,
        member_group_ids=frozenset({SALES_GROUP_ID}),
    )

    with pytest.raises(TenantIsolationError):
        can_claim_conversation(
            context,
            actor,
            make_conversation(tenant_id=TENANT_B_ID),
        )
