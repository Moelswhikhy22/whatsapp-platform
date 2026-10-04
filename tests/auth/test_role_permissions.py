from app.auth.permissions import Permission
from app.auth.role_permissions import ROLE_PERMISSIONS, permissions_for_role, role_has_permission
from app.auth.roles import Role


def test_every_supported_role_has_explicit_mapping() -> None:
    assert set(ROLE_PERMISSIONS) == set(Role)


def test_platform_admin_is_not_a_tenant_permission_wildcard() -> None:
    permissions = permissions_for_role(Role.PLATFORM_ADMIN)

    assert Permission.PLATFORM_TENANT_CREATE in permissions
    assert Permission.PLATFORM_TENANT_SUSPEND in permissions
    assert Permission.CONVERSATION_READ not in permissions
    assert Permission.MESSAGE_SEND not in permissions
    assert Permission.INTEGRATION_MANAGE not in permissions


def test_tenant_admin_has_full_tenant_administration_permissions() -> None:
    permissions = permissions_for_role(Role.TENANT_ADMIN)

    assert Permission.CONVERSATION_READ in permissions
    assert Permission.CONVERSATION_REASSIGN in permissions
    assert Permission.CUSTOMER_UPDATE in permissions
    assert Permission.GROUP_MANAGE_MEMBERS in permissions
    assert Permission.TEMPLATE_UPDATE in permissions
    assert Permission.INTEGRATION_MANAGE in permissions
    assert Permission.AUDIT_READ in permissions
    assert Permission.PLATFORM_TENANT_UPDATE not in permissions


def test_group_admin_has_group_operations_but_not_tenant_administration() -> None:
    permissions = permissions_for_role(Role.GROUP_ADMIN)

    assert Permission.CONVERSATION_REASSIGN in permissions
    assert Permission.CONVERSATION_TRANSFER in permissions
    assert Permission.GROUP_MANAGE_MEMBERS in permissions
    assert Permission.MESSAGE_SEND in permissions
    assert Permission.INTEGRATION_MANAGE not in permissions
    assert Permission.CUSTOMER_UPDATE in permissions
    assert Permission.PLATFORM_TENANT_READ not in permissions


def test_employee_is_operational_not_administrative() -> None:
    permissions = permissions_for_role(Role.EMPLOYEE)

    assert Permission.CONVERSATION_READ in permissions
    assert Permission.CONVERSATION_CLAIM in permissions
    assert Permission.MESSAGE_SEND in permissions
    assert Permission.CONVERSATION_ESCALATE in permissions
    assert Permission.GROUP_MANAGE_MEMBERS not in permissions
    assert Permission.CONVERSATION_REASSIGN not in permissions
    assert Permission.INTEGRATION_MANAGE not in permissions
    assert Permission.AUDIT_READ not in permissions


def test_integration_is_machine_capability_not_human_administration() -> None:
    permissions = permissions_for_role(Role.INTEGRATION)

    assert permissions == frozenset(
        {
            Permission.CONVERSATION_READ,
            Permission.MESSAGE_SEND,
            Permission.CUSTOMER_READ,
            Permission.WEBHOOK_MANAGE,
        }
    )
    assert Permission.CONVERSATION_CLAIM not in permissions
    assert Permission.GROUP_MANAGE_MEMBERS not in permissions
    assert Permission.PLATFORM_TENANT_READ not in permissions


def test_role_permission_helper_checks_rbac_only() -> None:
    assert role_has_permission(Role.EMPLOYEE, Permission.MESSAGE_SEND)
    assert not role_has_permission(Role.EMPLOYEE, Permission.INTEGRATION_MANAGE)
