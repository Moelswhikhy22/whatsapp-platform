from __future__ import annotations

from uuid import UUID

import pytest

from app.authorization import (
    AuthorizationContext,
    AuthorizationDeniedError,
    CustomerAccessResource,
    CustomerActorContext,
    Role,
    TenantIsolationError,
    can_modify_customer,
)

TENANT_A_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

TENANT_B_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")

SALES_GROUP_ID = UUID("11111111-1111-1111-1111-111111111111")

ACCOUNTING_GROUP_ID = UUID("22222222-2222-2222-2222-222222222222")

SUPPORT_GROUP_ID = UUID("55555555-5555-5555-5555-555555555555")


def make_customer(
    *,
    tenant_id: UUID = TENANT_A_ID,
    group_ids: frozenset[UUID] | None = None,
) -> CustomerAccessResource:
    if group_ids is None:
        group_ids = frozenset({SALES_GROUP_ID})

    return CustomerAccessResource(
        tenant_id=tenant_id,
        group_ids=group_ids,
    )


def test_tenant_admin_can_modify_customer_in_same_tenant() -> None:
    context = AuthorizationContext(
        actor_id="tenant-admin-123",
        role=Role.TENANT_ADMIN,
        tenant_id=TENANT_A_ID,
    )

    assert can_modify_customer(
        context,
        CustomerActorContext(),
        make_customer(),
    )


def test_tenant_admin_can_modify_customer_without_group_assignment() -> None:
    context = AuthorizationContext(
        actor_id="tenant-admin-123",
        role=Role.TENANT_ADMIN,
        tenant_id=TENANT_A_ID,
    )

    customer = make_customer(
        group_ids=frozenset(),
    )

    assert can_modify_customer(
        context,
        CustomerActorContext(),
        customer,
    )


def test_tenant_admin_cannot_modify_foreign_tenant_customer() -> None:
    context = AuthorizationContext(
        actor_id="tenant-admin-123",
        role=Role.TENANT_ADMIN,
        tenant_id=TENANT_A_ID,
    )

    with pytest.raises(TenantIsolationError):
        can_modify_customer(
            context,
            CustomerActorContext(),
            make_customer(
                tenant_id=TENANT_B_ID,
            ),
        )


def test_group_admin_can_modify_customer_in_administered_group() -> None:
    context = AuthorizationContext(
        actor_id="group-admin-sales",
        role=Role.GROUP_ADMIN,
        tenant_id=TENANT_A_ID,
    )

    actor = CustomerActorContext(
        administered_group_ids=frozenset({SALES_GROUP_ID}),
    )

    assert can_modify_customer(
        context,
        actor,
        make_customer(
            group_ids=frozenset({SALES_GROUP_ID}),
        ),
    )


def test_group_admin_cannot_modify_customer_outside_administered_groups() -> None:
    context = AuthorizationContext(
        actor_id="group-admin-sales",
        role=Role.GROUP_ADMIN,
        tenant_id=TENANT_A_ID,
    )

    actor = CustomerActorContext(
        administered_group_ids=frozenset({SALES_GROUP_ID}),
    )

    customer = make_customer(
        group_ids=frozenset({ACCOUNTING_GROUP_ID}),
    )

    assert not can_modify_customer(
        context,
        actor,
        customer,
    )


def test_group_admin_can_modify_multi_group_customer_when_one_group_matches() -> None:
    context = AuthorizationContext(
        actor_id="group-admin-sales",
        role=Role.GROUP_ADMIN,
        tenant_id=TENANT_A_ID,
    )

    actor = CustomerActorContext(
        administered_group_ids=frozenset({SALES_GROUP_ID}),
    )

    customer = make_customer(
        group_ids=frozenset(
            {
                SALES_GROUP_ID,
                SUPPORT_GROUP_ID,
                ACCOUNTING_GROUP_ID,
            }
        ),
    )

    assert can_modify_customer(
        context,
        actor,
        customer,
    )


def test_group_admin_can_modify_when_any_administered_group_matches() -> None:
    context = AuthorizationContext(
        actor_id="group-admin-multiple",
        role=Role.GROUP_ADMIN,
        tenant_id=TENANT_A_ID,
    )

    actor = CustomerActorContext(
        administered_group_ids=frozenset(
            {
                SALES_GROUP_ID,
                SUPPORT_GROUP_ID,
            }
        ),
    )

    customer = make_customer(
        group_ids=frozenset(
            {
                SUPPORT_GROUP_ID,
                ACCOUNTING_GROUP_ID,
            }
        ),
    )

    assert can_modify_customer(
        context,
        actor,
        customer,
    )


def test_group_admin_cannot_modify_customer_without_group_assignment() -> None:
    context = AuthorizationContext(
        actor_id="group-admin-sales",
        role=Role.GROUP_ADMIN,
        tenant_id=TENANT_A_ID,
    )

    actor = CustomerActorContext(
        administered_group_ids=frozenset({SALES_GROUP_ID}),
    )

    customer = make_customer(
        group_ids=frozenset(),
    )

    assert not can_modify_customer(
        context,
        actor,
        customer,
    )


def test_group_admin_without_administered_groups_cannot_modify_customer() -> None:
    context = AuthorizationContext(
        actor_id="group-admin-without-groups",
        role=Role.GROUP_ADMIN,
        tenant_id=TENANT_A_ID,
    )

    assert not can_modify_customer(
        context,
        CustomerActorContext(),
        make_customer(),
    )


def test_employee_cannot_modify_customer() -> None:
    context = AuthorizationContext(
        actor_id="employee-123",
        role=Role.EMPLOYEE,
        tenant_id=TENANT_A_ID,
    )

    with pytest.raises(AuthorizationDeniedError):
        can_modify_customer(
            context,
            CustomerActorContext(),
            make_customer(),
        )


def test_integration_cannot_modify_customer() -> None:
    context = AuthorizationContext(
        actor_id="integration-tenant-a",
        role=Role.INTEGRATION,
        tenant_id=TENANT_A_ID,
    )

    with pytest.raises(AuthorizationDeniedError):
        can_modify_customer(
            context,
            CustomerActorContext(),
            make_customer(),
        )


def test_platform_admin_has_no_implicit_customer_modify_access() -> None:
    context = AuthorizationContext(
        actor_id="platform-admin-123",
        role=Role.PLATFORM_ADMIN,
        tenant_id=TENANT_A_ID,
    )

    with pytest.raises(AuthorizationDeniedError):
        can_modify_customer(
            context,
            CustomerActorContext(),
            make_customer(),
        )


def test_foreign_tenant_is_rejected_before_group_acl() -> None:
    context = AuthorizationContext(
        actor_id="group-admin-without-access",
        role=Role.GROUP_ADMIN,
        tenant_id=TENANT_A_ID,
    )

    actor = CustomerActorContext(
        administered_group_ids=frozenset(),
    )

    with pytest.raises(TenantIsolationError):
        can_modify_customer(
            context,
            actor,
            make_customer(
                tenant_id=TENANT_B_ID,
                group_ids=frozenset(),
            ),
        )


def test_foreign_tenant_is_rejected_before_rbac() -> None:
    context = AuthorizationContext(
        actor_id="employee-123",
        role=Role.EMPLOYEE,
        tenant_id=TENANT_A_ID,
    )

    with pytest.raises(TenantIsolationError):
        can_modify_customer(
            context,
            CustomerActorContext(),
            make_customer(
                tenant_id=TENANT_B_ID,
            ),
        )
