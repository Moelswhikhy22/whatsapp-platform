from __future__ import annotations

from uuid import UUID

import pytest

from app.authorization import (
    AuthorizationContext,
    AuthorizationDeniedError,
    ConversationAccessResource,
    ConversationActorContext,
    ConversationTransferDestination,
    Role,
    TenantIsolationError,
    can_transfer_conversation,
)

TENANT_A_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

TENANT_B_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")

SALES_GROUP_ID = UUID("11111111-1111-1111-1111-111111111111")

ACCOUNTING_GROUP_ID = UUID("22222222-2222-2222-2222-222222222222")

SUPPORT_GROUP_ID = UUID("55555555-5555-5555-5555-555555555555")

AHMED_EMPLOYEE_ID = UUID("33333333-3333-3333-3333-333333333333")


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


def make_destination(
    *,
    tenant_id: UUID = TENANT_A_ID,
    group_id: UUID = ACCOUNTING_GROUP_ID,
) -> ConversationTransferDestination:
    return ConversationTransferDestination(
        tenant_id=tenant_id,
        group_id=group_id,
    )


def test_tenant_admin_can_transfer_between_groups_in_same_tenant() -> None:
    context = AuthorizationContext(
        actor_id="tenant-admin-123",
        role=Role.TENANT_ADMIN,
        tenant_id=TENANT_A_ID,
    )

    assert can_transfer_conversation(
        context,
        ConversationActorContext(),
        make_conversation(),
        make_destination(),
    )


def test_tenant_admin_cannot_transfer_to_same_group() -> None:
    context = AuthorizationContext(
        actor_id="tenant-admin-123",
        role=Role.TENANT_ADMIN,
        tenant_id=TENANT_A_ID,
    )

    destination = make_destination(
        group_id=SALES_GROUP_ID,
    )

    assert not can_transfer_conversation(
        context,
        ConversationActorContext(),
        make_conversation(),
        destination,
    )


def test_tenant_admin_cannot_transfer_to_foreign_tenant() -> None:
    context = AuthorizationContext(
        actor_id="tenant-admin-123",
        role=Role.TENANT_ADMIN,
        tenant_id=TENANT_A_ID,
    )

    destination = make_destination(
        tenant_id=TENANT_B_ID,
    )

    with pytest.raises(TenantIsolationError):
        can_transfer_conversation(
            context,
            ConversationActorContext(),
            make_conversation(),
            destination,
        )


def test_group_admin_can_transfer_from_administered_group() -> None:
    context = AuthorizationContext(
        actor_id="group-admin-sales",
        role=Role.GROUP_ADMIN,
        tenant_id=TENANT_A_ID,
    )

    actor = ConversationActorContext(
        administered_group_ids=frozenset({SALES_GROUP_ID}),
    )

    assert can_transfer_conversation(
        context,
        actor,
        make_conversation(),
        make_destination(),
    )


def test_group_admin_can_transfer_to_group_they_do_not_administer() -> None:
    context = AuthorizationContext(
        actor_id="group-admin-sales",
        role=Role.GROUP_ADMIN,
        tenant_id=TENANT_A_ID,
    )

    actor = ConversationActorContext(
        administered_group_ids=frozenset({SALES_GROUP_ID}),
    )

    destination = make_destination(
        group_id=SUPPORT_GROUP_ID,
    )

    assert can_transfer_conversation(
        context,
        actor,
        make_conversation(),
        destination,
    )


def test_group_admin_cannot_transfer_from_non_administered_group() -> None:
    context = AuthorizationContext(
        actor_id="group-admin-accounting",
        role=Role.GROUP_ADMIN,
        tenant_id=TENANT_A_ID,
    )

    actor = ConversationActorContext(
        administered_group_ids=frozenset({ACCOUNTING_GROUP_ID}),
    )

    assert not can_transfer_conversation(
        context,
        actor,
        make_conversation(
            group_id=SALES_GROUP_ID,
        ),
        make_destination(),
    )


def test_group_admin_does_not_need_operational_membership_to_transfer() -> None:
    context = AuthorizationContext(
        actor_id="group-admin-sales",
        role=Role.GROUP_ADMIN,
        tenant_id=TENANT_A_ID,
    )

    actor = ConversationActorContext(
        member_group_ids=frozenset({ACCOUNTING_GROUP_ID}),
        administered_group_ids=frozenset({SALES_GROUP_ID}),
    )

    assert can_transfer_conversation(
        context,
        actor,
        make_conversation(),
        make_destination(),
    )


def test_group_admin_cannot_transfer_to_foreign_tenant() -> None:
    context = AuthorizationContext(
        actor_id="group-admin-sales",
        role=Role.GROUP_ADMIN,
        tenant_id=TENANT_A_ID,
    )

    actor = ConversationActorContext(
        administered_group_ids=frozenset({SALES_GROUP_ID}),
    )

    destination = make_destination(
        tenant_id=TENANT_B_ID,
    )

    with pytest.raises(TenantIsolationError):
        can_transfer_conversation(
            context,
            actor,
            make_conversation(),
            destination,
        )


def test_employee_cannot_transfer_conversation() -> None:
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
        can_transfer_conversation(
            context,
            actor,
            make_conversation(),
            make_destination(),
        )


def test_integration_cannot_transfer_conversation() -> None:
    context = AuthorizationContext(
        actor_id="integration-tenant-a",
        role=Role.INTEGRATION,
        tenant_id=TENANT_A_ID,
    )

    with pytest.raises(AuthorizationDeniedError):
        can_transfer_conversation(
            context,
            ConversationActorContext(),
            make_conversation(),
            make_destination(),
        )


def test_platform_admin_has_no_implicit_transfer_permission() -> None:
    context = AuthorizationContext(
        actor_id="platform-admin-123",
        role=Role.PLATFORM_ADMIN,
        tenant_id=TENANT_A_ID,
    )

    with pytest.raises(AuthorizationDeniedError):
        can_transfer_conversation(
            context,
            ConversationActorContext(),
            make_conversation(),
            make_destination(),
        )


def test_foreign_conversation_is_rejected_before_transfer_acl() -> None:
    context = AuthorizationContext(
        actor_id="group-admin-sales",
        role=Role.GROUP_ADMIN,
        tenant_id=TENANT_A_ID,
    )

    actor = ConversationActorContext(
        administered_group_ids=frozenset(),
    )

    with pytest.raises(TenantIsolationError):
        can_transfer_conversation(
            context,
            actor,
            make_conversation(
                tenant_id=TENANT_B_ID,
            ),
            make_destination(),
        )


def test_foreign_conversation_is_rejected_before_destination_check() -> None:
    context = AuthorizationContext(
        actor_id="tenant-admin-123",
        role=Role.TENANT_ADMIN,
        tenant_id=TENANT_A_ID,
    )

    foreign_conversation = make_conversation(
        tenant_id=TENANT_B_ID,
    )

    foreign_destination = make_destination(
        tenant_id=TENANT_B_ID,
    )

    with pytest.raises(TenantIsolationError):
        can_transfer_conversation(
            context,
            ConversationActorContext(),
            foreign_conversation,
            foreign_destination,
        )
