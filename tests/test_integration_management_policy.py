from __future__ import annotations

from uuid import UUID

import pytest

from app.authorization import (
    AuthorizationContext,
    AuthorizationDeniedError,
    IntegrationAccessResource,
    IntegrationAction,
    Role,
    TenantIsolationError,
    can_manage_integrations,
)

TENANT_A_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

TENANT_B_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


def make_integration(
    *,
    tenant_id: UUID = TENANT_A_ID,
) -> IntegrationAccessResource:
    return IntegrationAccessResource(
        tenant_id=tenant_id,
    )


@pytest.mark.parametrize(
    "action",
    [
        IntegrationAction.READ,
        IntegrationAction.CREATE,
        IntegrationAction.UPDATE,
        IntegrationAction.VALIDATE,
        IntegrationAction.CREDENTIALS_UPDATE,
    ],
)
def test_tenant_admin_can_manage_integration(
    action: IntegrationAction,
) -> None:
    context = AuthorizationContext(
        actor_id="tenant-admin-123",
        role=Role.TENANT_ADMIN,
        tenant_id=TENANT_A_ID,
    )

    assert can_manage_integrations(
        context,
        make_integration(),
        action,
    )


def test_tenant_admin_can_read_integration() -> None:
    context = AuthorizationContext(
        actor_id="tenant-admin-123",
        role=Role.TENANT_ADMIN,
        tenant_id=TENANT_A_ID,
    )

    assert can_manage_integrations(
        context,
        make_integration(),
        IntegrationAction.READ,
    )


def test_tenant_admin_can_create_integration() -> None:
    context = AuthorizationContext(
        actor_id="tenant-admin-123",
        role=Role.TENANT_ADMIN,
        tenant_id=TENANT_A_ID,
    )

    assert can_manage_integrations(
        context,
        make_integration(),
        IntegrationAction.CREATE,
    )


def test_tenant_admin_can_update_integration() -> None:
    context = AuthorizationContext(
        actor_id="tenant-admin-123",
        role=Role.TENANT_ADMIN,
        tenant_id=TENANT_A_ID,
    )

    assert can_manage_integrations(
        context,
        make_integration(),
        IntegrationAction.UPDATE,
    )


def test_tenant_admin_can_validate_integration() -> None:
    context = AuthorizationContext(
        actor_id="tenant-admin-123",
        role=Role.TENANT_ADMIN,
        tenant_id=TENANT_A_ID,
    )

    assert can_manage_integrations(
        context,
        make_integration(),
        IntegrationAction.VALIDATE,
    )


def test_tenant_admin_can_update_integration_credentials() -> None:
    context = AuthorizationContext(
        actor_id="tenant-admin-123",
        role=Role.TENANT_ADMIN,
        tenant_id=TENANT_A_ID,
    )

    assert can_manage_integrations(
        context,
        make_integration(),
        IntegrationAction.CREDENTIALS_UPDATE,
    )


def test_tenant_admin_cannot_manage_foreign_integration() -> None:
    context = AuthorizationContext(
        actor_id="tenant-admin-123",
        role=Role.TENANT_ADMIN,
        tenant_id=TENANT_A_ID,
    )

    with pytest.raises(TenantIsolationError):
        can_manage_integrations(
            context,
            make_integration(
                tenant_id=TENANT_B_ID,
            ),
            IntegrationAction.UPDATE,
        )


@pytest.mark.parametrize(
    "action",
    [
        IntegrationAction.READ,
        IntegrationAction.CREATE,
        IntegrationAction.UPDATE,
        IntegrationAction.VALIDATE,
        IntegrationAction.CREDENTIALS_UPDATE,
    ],
)
def test_foreign_integration_is_rejected_for_every_action(
    action: IntegrationAction,
) -> None:
    context = AuthorizationContext(
        actor_id="tenant-admin-123",
        role=Role.TENANT_ADMIN,
        tenant_id=TENANT_A_ID,
    )

    with pytest.raises(TenantIsolationError):
        can_manage_integrations(
            context,
            make_integration(
                tenant_id=TENANT_B_ID,
            ),
            action,
        )


def test_group_admin_cannot_read_integrations() -> None:
    context = AuthorizationContext(
        actor_id="group-admin-123",
        role=Role.GROUP_ADMIN,
        tenant_id=TENANT_A_ID,
    )

    with pytest.raises(AuthorizationDeniedError):
        can_manage_integrations(
            context,
            make_integration(),
            IntegrationAction.READ,
        )


def test_group_admin_cannot_update_integrations() -> None:
    context = AuthorizationContext(
        actor_id="group-admin-123",
        role=Role.GROUP_ADMIN,
        tenant_id=TENANT_A_ID,
    )

    with pytest.raises(AuthorizationDeniedError):
        can_manage_integrations(
            context,
            make_integration(),
            IntegrationAction.UPDATE,
        )


def test_group_admin_cannot_update_credentials() -> None:
    context = AuthorizationContext(
        actor_id="group-admin-123",
        role=Role.GROUP_ADMIN,
        tenant_id=TENANT_A_ID,
    )

    with pytest.raises(AuthorizationDeniedError):
        can_manage_integrations(
            context,
            make_integration(),
            IntegrationAction.CREDENTIALS_UPDATE,
        )


def test_employee_cannot_manage_integrations() -> None:
    context = AuthorizationContext(
        actor_id="employee-123",
        role=Role.EMPLOYEE,
        tenant_id=TENANT_A_ID,
    )

    with pytest.raises(AuthorizationDeniedError):
        can_manage_integrations(
            context,
            make_integration(),
            IntegrationAction.UPDATE,
        )


def test_employee_cannot_update_integration_credentials() -> None:
    context = AuthorizationContext(
        actor_id="employee-123",
        role=Role.EMPLOYEE,
        tenant_id=TENANT_A_ID,
    )

    with pytest.raises(AuthorizationDeniedError):
        can_manage_integrations(
            context,
            make_integration(),
            IntegrationAction.CREDENTIALS_UPDATE,
        )


def test_integration_identity_cannot_manage_itself() -> None:
    context = AuthorizationContext(
        actor_id="odoo-tenant-a",
        role=Role.INTEGRATION,
        tenant_id=TENANT_A_ID,
    )

    with pytest.raises(AuthorizationDeniedError):
        can_manage_integrations(
            context,
            make_integration(),
            IntegrationAction.UPDATE,
        )


def test_integration_identity_cannot_rotate_its_credentials() -> None:
    context = AuthorizationContext(
        actor_id="odoo-tenant-a",
        role=Role.INTEGRATION,
        tenant_id=TENANT_A_ID,
    )

    with pytest.raises(AuthorizationDeniedError):
        can_manage_integrations(
            context,
            make_integration(),
            IntegrationAction.CREDENTIALS_UPDATE,
        )


def test_platform_admin_has_no_implicit_integration_access() -> None:
    context = AuthorizationContext(
        actor_id="platform-admin-123",
        role=Role.PLATFORM_ADMIN,
        tenant_id=TENANT_A_ID,
    )

    with pytest.raises(AuthorizationDeniedError):
        can_manage_integrations(
            context,
            make_integration(),
            IntegrationAction.READ,
        )


def test_foreign_tenant_is_rejected_before_rbac() -> None:
    context = AuthorizationContext(
        actor_id="employee-123",
        role=Role.EMPLOYEE,
        tenant_id=TENANT_A_ID,
    )

    with pytest.raises(TenantIsolationError):
        can_manage_integrations(
            context,
            make_integration(
                tenant_id=TENANT_B_ID,
            ),
            IntegrationAction.UPDATE,
        )
