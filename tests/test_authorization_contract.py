from __future__ import annotations

from uuid import UUID

import pytest

from app.authorization import (
    ROLE_PERMISSIONS,
    AuthorizationContext,
    AuthorizationDeniedError,
    Permission,
    Role,
    TenantIsolationError,
    require_tenant_permission,
    role_has_permission,
)

TENANT_A_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

TENANT_B_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


EXPECTED_ROLE_PERMISSIONS: dict[
    Role,
    frozenset[Permission],
] = {
    Role.PLATFORM_ADMIN: frozenset(
        {
            Permission.PLATFORM_TENANT_CREATE,
            Permission.PLATFORM_TENANT_READ,
            Permission.PLATFORM_TENANT_UPDATE,
            Permission.PLATFORM_TENANT_SUSPEND,
            Permission.AUDIT_READ,
        }
    ),
    Role.TENANT_ADMIN: frozenset(
        {
            Permission.TENANT_READ,
            Permission.TENANT_UPDATE,
            Permission.CONVERSATION_READ,
            Permission.CONVERSATION_CLAIM,
            Permission.CONVERSATION_CLOSE,
            Permission.CONVERSATION_REOPEN,
            Permission.CONVERSATION_REASSIGN,
            Permission.CONVERSATION_TRANSFER,
            Permission.CONVERSATION_ESCALATE,
            Permission.MESSAGE_SEND,
            Permission.CUSTOMER_READ,
            Permission.CUSTOMER_UPDATE,
            Permission.GROUP_READ,
            Permission.GROUP_MANAGE,
            Permission.GROUP_MANAGE_MEMBERS,
            Permission.EMPLOYEE_READ,
            Permission.EMPLOYEE_MANAGE,
            Permission.TEMPLATE_READ,
            Permission.TEMPLATE_CREATE,
            Permission.TEMPLATE_UPDATE,
            Permission.TEMPLATE_SUBMIT,
            Permission.TEMPLATE_SEND,
            Permission.MEDIA_READ,
            Permission.INTEGRATION_READ,
            Permission.INTEGRATION_MANAGE,
            Permission.INTEGRATION_CREDENTIALS_UPDATE,
            Permission.WEBHOOK_MANAGE,
            Permission.AUDIT_READ,
        }
    ),
    Role.GROUP_ADMIN: frozenset(
        {
            Permission.CONVERSATION_READ,
            Permission.CONVERSATION_CLAIM,
            Permission.CONVERSATION_CLOSE,
            Permission.CONVERSATION_REOPEN,
            Permission.CONVERSATION_REASSIGN,
            Permission.CONVERSATION_TRANSFER,
            Permission.CONVERSATION_ESCALATE,
            Permission.MESSAGE_SEND,
            Permission.CUSTOMER_READ,
            Permission.CUSTOMER_UPDATE,
            Permission.GROUP_READ,
            Permission.GROUP_MANAGE_MEMBERS,
            Permission.EMPLOYEE_READ,
            Permission.TEMPLATE_READ,
            Permission.TEMPLATE_CREATE,
            Permission.TEMPLATE_UPDATE,
            Permission.TEMPLATE_SEND,
            Permission.MEDIA_READ,
            Permission.AUDIT_READ,
        }
    ),
    Role.EMPLOYEE: frozenset(
        {
            Permission.CONVERSATION_READ,
            Permission.CONVERSATION_CLAIM,
            Permission.CONVERSATION_CLOSE,
            Permission.CONVERSATION_ESCALATE,
            Permission.MESSAGE_SEND,
            Permission.CUSTOMER_READ,
            Permission.GROUP_READ,
            Permission.TEMPLATE_READ,
            Permission.TEMPLATE_SEND,
            Permission.MEDIA_READ,
        }
    ),
    Role.INTEGRATION: frozenset(
        {
            Permission.CONVERSATION_READ,
            Permission.MESSAGE_SEND,
            Permission.CUSTOMER_READ,
            Permission.WEBHOOK_MANAGE,
        }
    ),
}


@pytest.mark.parametrize(
    ("role", "expected_permissions"),
    EXPECTED_ROLE_PERMISSIONS.items(),
)
def test_role_permission_matrix_is_exact(
    role: Role,
    expected_permissions: frozenset[Permission],
) -> None:
    assert ROLE_PERMISSIONS[role] == expected_permissions


def test_every_role_has_an_explicit_permission_mapping() -> None:
    assert set(ROLE_PERMISSIONS) == set(Role)


@pytest.mark.parametrize(
    "role",
    list(Role),
)
def test_role_has_permission_matches_permission_matrix(
    role: Role,
) -> None:
    for permission in Permission:
        assert role_has_permission(
            role,
            permission,
        ) is (permission in EXPECTED_ROLE_PERMISSIONS[role])


def test_platform_admin_has_platform_tenant_permissions() -> None:
    expected_platform_permissions = {
        Permission.PLATFORM_TENANT_CREATE,
        Permission.PLATFORM_TENANT_READ,
        Permission.PLATFORM_TENANT_UPDATE,
        Permission.PLATFORM_TENANT_SUSPEND,
    }

    for permission in expected_platform_permissions:
        assert role_has_permission(
            Role.PLATFORM_ADMIN,
            permission,
        )


def test_platform_admin_has_no_implicit_tenant_business_access() -> None:
    forbidden_permissions = {
        Permission.CONVERSATION_READ,
        Permission.CONVERSATION_CLAIM,
        Permission.CONVERSATION_REASSIGN,
        Permission.CONVERSATION_TRANSFER,
        Permission.MESSAGE_SEND,
        Permission.CUSTOMER_READ,
        Permission.CUSTOMER_UPDATE,
        Permission.GROUP_MANAGE,
        Permission.EMPLOYEE_MANAGE,
        Permission.TEMPLATE_READ,
        Permission.TEMPLATE_CREATE,
        Permission.TEMPLATE_UPDATE,
        Permission.TEMPLATE_SUBMIT,
        Permission.TEMPLATE_SEND,
        Permission.MEDIA_READ,
        Permission.INTEGRATION_READ,
        Permission.INTEGRATION_MANAGE,
        Permission.INTEGRATION_CREDENTIALS_UPDATE,
        Permission.WEBHOOK_MANAGE,
    }

    for permission in forbidden_permissions:
        assert not role_has_permission(
            Role.PLATFORM_ADMIN,
            permission,
        )


def test_platform_admin_does_not_use_tenant_scoped_permissions() -> None:
    tenant_scoped_permissions = {
        Permission.TENANT_CREATE,
        Permission.TENANT_READ,
        Permission.TENANT_UPDATE,
        Permission.TENANT_SUSPEND,
    }

    for permission in tenant_scoped_permissions:
        assert not role_has_permission(
            Role.PLATFORM_ADMIN,
            permission,
        )


def test_tenant_admin_has_no_platform_tenant_permissions() -> None:
    platform_permissions = {
        Permission.PLATFORM_TENANT_CREATE,
        Permission.PLATFORM_TENANT_READ,
        Permission.PLATFORM_TENANT_UPDATE,
        Permission.PLATFORM_TENANT_SUSPEND,
    }

    for permission in platform_permissions:
        assert not role_has_permission(
            Role.TENANT_ADMIN,
            permission,
        )


def test_tenant_admin_cannot_create_or_suspend_tenants() -> None:
    assert not role_has_permission(
        Role.TENANT_ADMIN,
        Permission.TENANT_CREATE,
    )

    assert not role_has_permission(
        Role.TENANT_ADMIN,
        Permission.TENANT_SUSPEND,
    )


def test_group_admin_has_no_tenant_wide_integration_management() -> None:
    forbidden_permissions = {
        Permission.INTEGRATION_READ,
        Permission.INTEGRATION_MANAGE,
        Permission.INTEGRATION_CREDENTIALS_UPDATE,
    }

    for permission in forbidden_permissions:
        assert not role_has_permission(
            Role.GROUP_ADMIN,
            permission,
        )


def test_group_admin_cannot_submit_meta_templates() -> None:
    assert not role_has_permission(
        Role.GROUP_ADMIN,
        Permission.TEMPLATE_SUBMIT,
    )


def test_employee_has_no_administrative_permissions() -> None:
    forbidden_permissions = {
        Permission.TENANT_CREATE,
        Permission.TENANT_UPDATE,
        Permission.TENANT_SUSPEND,
        Permission.CONVERSATION_REASSIGN,
        Permission.CONVERSATION_TRANSFER,
        Permission.CUSTOMER_UPDATE,
        Permission.GROUP_MANAGE,
        Permission.GROUP_MANAGE_MEMBERS,
        Permission.EMPLOYEE_MANAGE,
        Permission.TEMPLATE_CREATE,
        Permission.TEMPLATE_UPDATE,
        Permission.TEMPLATE_SUBMIT,
        Permission.INTEGRATION_READ,
        Permission.INTEGRATION_MANAGE,
        Permission.INTEGRATION_CREDENTIALS_UPDATE,
        Permission.WEBHOOK_MANAGE,
        Permission.AUDIT_READ,
    }

    for permission in forbidden_permissions:
        assert not role_has_permission(
            Role.EMPLOYEE,
            permission,
        )


def test_integration_role_stays_least_privilege() -> None:
    assert EXPECTED_ROLE_PERMISSIONS[Role.INTEGRATION] == frozenset(
        {
            Permission.CONVERSATION_READ,
            Permission.MESSAGE_SEND,
            Permission.CUSTOMER_READ,
            Permission.WEBHOOK_MANAGE,
        }
    )


def test_integration_identity_cannot_manage_integrations() -> None:
    assert not role_has_permission(
        Role.INTEGRATION,
        Permission.INTEGRATION_MANAGE,
    )

    assert not role_has_permission(
        Role.INTEGRATION,
        Permission.INTEGRATION_CREDENTIALS_UPDATE,
    )


def test_integration_identity_cannot_modify_customers() -> None:
    assert role_has_permission(
        Role.INTEGRATION,
        Permission.CUSTOMER_READ,
    )

    assert not role_has_permission(
        Role.INTEGRATION,
        Permission.CUSTOMER_UPDATE,
    )


def test_integration_identity_has_no_template_permissions() -> None:
    template_permissions = {
        Permission.TEMPLATE_READ,
        Permission.TEMPLATE_CREATE,
        Permission.TEMPLATE_UPDATE,
        Permission.TEMPLATE_SUBMIT,
        Permission.TEMPLATE_SEND,
    }

    for permission in template_permissions:
        assert not role_has_permission(
            Role.INTEGRATION,
            permission,
        )


def test_tenant_isolation_happens_before_rbac() -> None:
    context = AuthorizationContext(
        actor_id="employee-123",
        role=Role.EMPLOYEE,
        tenant_id=TENANT_A_ID,
    )

    with pytest.raises(TenantIsolationError):
        require_tenant_permission(
            context,
            TENANT_B_ID,
            Permission.INTEGRATION_MANAGE,
        )


def test_same_tenant_missing_permission_is_authorization_denied() -> None:
    context = AuthorizationContext(
        actor_id="employee-123",
        role=Role.EMPLOYEE,
        tenant_id=TENANT_A_ID,
    )

    with pytest.raises(AuthorizationDeniedError):
        require_tenant_permission(
            context,
            TENANT_A_ID,
            Permission.INTEGRATION_MANAGE,
        )


def test_missing_tenant_context_is_never_treated_as_tenant_access() -> None:
    context = AuthorizationContext(
        actor_id="platform-admin-123",
        role=Role.PLATFORM_ADMIN,
        tenant_id=None,
    )

    with pytest.raises(TenantIsolationError):
        require_tenant_permission(
            context,
            TENANT_A_ID,
            Permission.TENANT_READ,
        )
