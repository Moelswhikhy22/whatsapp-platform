from __future__ import annotations

from uuid import UUID

import pytest

from app.authorization import (
    AuthorizationContext,
    AuthorizationDeniedError,
    Permission,
    Role,
    TenantIsolationError,
    has_permission,
    require_permission,
    require_tenant_permission,
)

TENANT_A_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

TENANT_B_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


def test_has_permission_returns_true_for_granted_permission() -> None:
    context = AuthorizationContext(
        actor_id="employee-123",
        role=Role.EMPLOYEE,
        tenant_id=TENANT_A_ID,
    )

    assert has_permission(
        context,
        Permission.MESSAGE_SEND,
    )


def test_has_permission_returns_false_for_missing_permission() -> None:
    context = AuthorizationContext(
        actor_id="employee-123",
        role=Role.EMPLOYEE,
        tenant_id=TENANT_A_ID,
    )

    assert not has_permission(
        context,
        Permission.INTEGRATION_MANAGE,
    )


def test_require_permission_allows_granted_permission() -> None:
    context = AuthorizationContext(
        actor_id="employee-123",
        role=Role.EMPLOYEE,
        tenant_id=TENANT_A_ID,
    )

    require_permission(
        context,
        Permission.MESSAGE_SEND,
    )


def test_require_permission_rejects_missing_permission() -> None:
    context = AuthorizationContext(
        actor_id="employee-123",
        role=Role.EMPLOYEE,
        tenant_id=TENANT_A_ID,
    )

    with pytest.raises(AuthorizationDeniedError) as exc_info:
        require_permission(
            context,
            Permission.INTEGRATION_MANAGE,
        )

    assert exc_info.value.permission is Permission.INTEGRATION_MANAGE


def test_authorization_denied_message_is_generic() -> None:
    context = AuthorizationContext(
        actor_id="employee-123",
        role=Role.EMPLOYEE,
        tenant_id=TENANT_A_ID,
    )

    with pytest.raises(AuthorizationDeniedError) as exc_info:
        require_permission(
            context,
            Permission.INTEGRATION_MANAGE,
        )

    assert str(exc_info.value) == "Authorization denied."


def test_require_tenant_permission_allows_same_tenant_with_permission() -> None:
    context = AuthorizationContext(
        actor_id="employee-123",
        role=Role.EMPLOYEE,
        tenant_id=TENANT_A_ID,
    )

    require_tenant_permission(
        context,
        TENANT_A_ID,
        Permission.MESSAGE_SEND,
    )


def test_require_tenant_permission_rejects_foreign_tenant() -> None:
    context = AuthorizationContext(
        actor_id="employee-123",
        role=Role.EMPLOYEE,
        tenant_id=TENANT_A_ID,
    )

    with pytest.raises(TenantIsolationError):
        require_tenant_permission(
            context,
            TENANT_B_ID,
            Permission.MESSAGE_SEND,
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


def test_missing_tenant_context_fails_closed() -> None:
    context = AuthorizationContext(
        actor_id="platform-admin-123",
        role=Role.PLATFORM_ADMIN,
    )

    with pytest.raises(TenantIsolationError):
        require_tenant_permission(
            context,
            TENANT_A_ID,
            Permission.CONVERSATION_READ,
        )


def test_platform_admin_does_not_bypass_tenant_boundary() -> None:
    context = AuthorizationContext(
        actor_id="platform-admin-123",
        role=Role.PLATFORM_ADMIN,
    )

    with pytest.raises(TenantIsolationError):
        require_tenant_permission(
            context,
            TENANT_A_ID,
            Permission.AUDIT_READ,
        )


def test_permission_is_granted_when_any_role_grants_it() -> None:
    context = AuthorizationContext(
        actor_id="multi-role-user",
        roles=frozenset(
            {
                Role.EMPLOYEE,
                Role.GROUP_ADMIN,
            }
        ),
        tenant_id=TENANT_A_ID,
    )

    assert has_permission(
        context,
        Permission.CONVERSATION_REASSIGN,
    )


def test_permission_is_denied_when_no_role_grants_it() -> None:
    context = AuthorizationContext(
        actor_id="multi-role-user",
        roles=frozenset(
            {
                Role.EMPLOYEE,
                Role.GROUP_ADMIN,
            }
        ),
        tenant_id=TENANT_A_ID,
    )

    assert not has_permission(
        context,
        Permission.INTEGRATION_MANAGE,
    )
