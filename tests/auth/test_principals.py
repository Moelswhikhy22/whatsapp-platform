from uuid import UUID

import pytest

from app.auth.permissions import Permission
from app.auth.principals import (
    ActorType,
    HumanPrincipal,
    IntegrationPrincipal,
)
from app.auth.roles import Role


def test_human_principal_has_human_actor_type() -> None:
    principal = HumanPrincipal(
        subject="keycloak-user-123",
        roles=frozenset({Role.EMPLOYEE}),
    )

    assert principal.actor_type is ActorType.HUMAN


def test_human_principal_resolves_permissions_from_roles() -> None:
    principal = HumanPrincipal(
        subject="keycloak-user-123",
        roles=frozenset({Role.EMPLOYEE}),
    )

    assert principal.has_permission(Permission.CONVERSATION_READ)
    assert principal.has_permission(Permission.MESSAGE_SEND)


def test_human_principal_rejects_integration_role() -> None:
    with pytest.raises(
        ValueError,
        match="integration role cannot be assigned",
    ):
        HumanPrincipal(
            subject="keycloak-user-123",
            roles=frozenset({Role.INTEGRATION}),
        )


def test_human_principal_requires_role() -> None:
    with pytest.raises(
        ValueError,
        match="must have at least one role",
    ):
        HumanPrincipal(
            subject="keycloak-user-123",
            roles=frozenset(),
        )


def test_human_principal_requires_subject() -> None:
    with pytest.raises(
        ValueError,
        match="subject must not be empty",
    ):
        HumanPrincipal(
            subject="   ",
            roles=frozenset({Role.EMPLOYEE}),
        )


def test_human_principal_can_have_employee_mapping() -> None:
    employee_id = UUID("00000000-0000-0000-0000-000000000101")

    principal = HumanPrincipal(
        subject="keycloak-user-123",
        roles=frozenset({Role.EMPLOYEE}),
        employee_id=employee_id,
    )

    assert principal.employee_id == employee_id


def test_integration_principal_has_machine_actor_type() -> None:
    principal = IntegrationPrincipal(
        integration_id=UUID("00000000-0000-0000-0000-000000000201"),
        tenant_id=UUID("00000000-0000-0000-0000-000000000301"),
        client_id="odoo-tenant-a",
        provider="odoo",
        permissions=frozenset(
            {
                Permission.CONVERSATION_READ,
                Permission.MESSAGE_SEND,
            }
        ),
    )

    assert principal.actor_type is ActorType.INTEGRATION
    assert principal.role is Role.INTEGRATION


def test_integration_principal_is_tenant_bound() -> None:
    tenant_id = UUID("00000000-0000-0000-0000-000000000301")

    principal = IntegrationPrincipal(
        integration_id=UUID("00000000-0000-0000-0000-000000000201"),
        tenant_id=tenant_id,
        client_id="odoo-tenant-a",
        provider="odoo",
        permissions=frozenset(
            {
                Permission.CONVERSATION_READ,
            }
        ),
    )

    assert principal.tenant_id == tenant_id


def test_integration_can_have_reduced_permissions() -> None:
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

    assert principal.has_permission(Permission.CONVERSATION_READ)

    assert not principal.has_permission(Permission.MESSAGE_SEND)


def test_integration_cannot_receive_employee_only_permission() -> None:
    with pytest.raises(
        ValueError,
        match="not allowed for Integration role",
    ):
        IntegrationPrincipal(
            integration_id=UUID("00000000-0000-0000-0000-000000000201"),
            tenant_id=UUID("00000000-0000-0000-0000-000000000301"),
            client_id="odoo-tenant-a",
            provider="odoo",
            permissions=frozenset(
                {
                    Permission.CONVERSATION_CLAIM,
                }
            ),
        )


def test_integration_cannot_receive_platform_permission() -> None:
    with pytest.raises(
        ValueError,
        match="not allowed for Integration role",
    ):
        IntegrationPrincipal(
            integration_id=UUID("00000000-0000-0000-0000-000000000201"),
            tenant_id=UUID("00000000-0000-0000-0000-000000000301"),
            client_id="odoo-tenant-a",
            provider="odoo",
            permissions=frozenset(
                {
                    Permission.PLATFORM_TENANT_UPDATE,
                }
            ),
        )
