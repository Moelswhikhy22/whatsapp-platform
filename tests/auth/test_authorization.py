from uuid import UUID

import pytest

from app.auth.authorization import (
    has_permission,
    require_permission,
)
from app.auth.exceptions import PermissionDeniedError
from app.auth.permissions import Permission
from app.auth.principals import (
    HumanPrincipal,
    IntegrationPrincipal,
)
from app.auth.roles import Role


def test_human_principal_has_allowed_permission() -> None:
    principal = HumanPrincipal(
        subject="keycloak-user-123",
        roles=frozenset({Role.EMPLOYEE}),
    )

    assert has_permission(
        principal,
        Permission.CONVERSATION_READ,
    )


def test_human_principal_missing_permission_returns_false() -> None:
    principal = HumanPrincipal(
        subject="keycloak-user-123",
        roles=frozenset({Role.EMPLOYEE}),
    )

    assert not has_permission(
        principal,
        Permission.INTEGRATION_MANAGE,
    )


def test_require_permission_allows_authorized_human() -> None:
    principal = HumanPrincipal(
        subject="keycloak-user-123",
        roles=frozenset({Role.EMPLOYEE}),
    )

    require_permission(
        principal,
        Permission.MESSAGE_SEND,
    )


def test_require_permission_rejects_unauthorized_human() -> None:
    principal = HumanPrincipal(
        subject="keycloak-user-123",
        roles=frozenset({Role.EMPLOYEE}),
    )

    with pytest.raises(PermissionDeniedError) as exc_info:
        require_permission(
            principal,
            Permission.INTEGRATION_MANAGE,
        )

    assert exc_info.value.permission is Permission.INTEGRATION_MANAGE

    assert exc_info.value.code == "PERMISSION_DENIED"


def test_integration_is_checked_using_its_actual_permissions() -> None:
    principal = IntegrationPrincipal(
        integration_id=UUID("00000000-0000-0000-0000-000000000201"),
        tenant_id=UUID("00000000-0000-0000-0000-000000000301"),
        client_id="odoo-tenant-a",
        provider="odoo",
        permissions=frozenset(
            {
                Permission.CONVERSATION_READ,
            }
        ),
    )

    assert has_permission(
        principal,
        Permission.CONVERSATION_READ,
    )

    assert not has_permission(
        principal,
        Permission.MESSAGE_SEND,
    )


def test_require_permission_rejects_integration_missing_scope() -> None:
    principal = IntegrationPrincipal(
        integration_id=UUID("00000000-0000-0000-0000-000000000201"),
        tenant_id=UUID("00000000-0000-0000-0000-000000000301"),
        client_id="odoo-tenant-a",
        provider="odoo",
        permissions=frozenset(
            {
                Permission.CONVERSATION_READ,
            }
        ),
    )

    with pytest.raises(PermissionDeniedError):
        require_permission(
            principal,
            Permission.MESSAGE_SEND,
        )


def test_permission_checker_does_not_implement_resource_acl() -> None:
    """
    RBAC permission success does not mean resource authorization success.

    Conversation ownership, tenant isolation, and group scope will be
    checked by resource policies later.
    """

    principal = HumanPrincipal(
        subject="keycloak-user-123",
        roles=frozenset({Role.EMPLOYEE}),
    )

    assert has_permission(
        principal,
        Permission.MESSAGE_SEND,
    )
