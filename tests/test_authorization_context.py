from __future__ import annotations

from dataclasses import FrozenInstanceError
from uuid import UUID

import pytest

from app.authorization import (
    AuthorizationContext,
    Role,
)

TENANT_A_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


def test_authorization_context_stores_actor_state() -> None:
    context = AuthorizationContext(
        actor_id="keycloak-user-123",
        role=Role.EMPLOYEE,
        tenant_id=TENANT_A_ID,
    )

    assert context.actor_id == "keycloak-user-123"
    assert context.role is Role.EMPLOYEE
    assert context.tenant_id == TENANT_A_ID


def test_authorization_context_is_immutable() -> None:
    context = AuthorizationContext(
        actor_id="keycloak-user-123",
        role=Role.EMPLOYEE,
        tenant_id=TENANT_A_ID,
    )

    with pytest.raises(FrozenInstanceError):
        context.tenant_id = None  # type: ignore[misc]


def test_authorization_context_rejects_empty_actor_id() -> None:
    with pytest.raises(
        ValueError,
        match="actor_id must not be empty",
    ):
        AuthorizationContext(
            actor_id="",
            role=Role.EMPLOYEE,
            tenant_id=TENANT_A_ID,
        )


def test_authorization_context_rejects_whitespace_actor_id() -> None:
    with pytest.raises(
        ValueError,
        match="actor_id must not be empty",
    ):
        AuthorizationContext(
            actor_id="   ",
            role=Role.EMPLOYEE,
            tenant_id=TENANT_A_ID,
        )


def test_platform_actor_may_exist_without_tenant_context() -> None:
    context = AuthorizationContext(
        actor_id="platform-admin-123",
        role=Role.PLATFORM_ADMIN,
    )

    assert context.tenant_id is None


def test_authorization_context_supports_multiple_roles() -> None:
    context = AuthorizationContext(
        actor_id="keycloak-user-123",
        roles=frozenset(
            {
                Role.EMPLOYEE,
                Role.GROUP_ADMIN,
            }
        ),
        tenant_id=TENANT_A_ID,
    )

    assert context.roles == frozenset(
        {
            Role.EMPLOYEE,
            Role.GROUP_ADMIN,
        }
    )

    assert context.has_role(Role.EMPLOYEE)
    assert context.has_role(Role.GROUP_ADMIN)
    assert not context.has_role(Role.TENANT_ADMIN)


def test_authorization_context_single_role_remains_backward_compatible() -> None:
    context = AuthorizationContext(
        actor_id="keycloak-user-123",
        role=Role.EMPLOYEE,
        tenant_id=TENANT_A_ID,
    )

    assert context.roles == frozenset(
        {
            Role.EMPLOYEE,
        }
    )

    assert context.role is Role.EMPLOYEE


def test_authorization_context_rejects_role_and_roles_together() -> None:
    with pytest.raises(
        ValueError,
        match="either role or roles",
    ):
        AuthorizationContext(
            actor_id="keycloak-user-123",
            role=Role.EMPLOYEE,
            roles=frozenset(
                {
                    Role.GROUP_ADMIN,
                }
            ),
            tenant_id=TENANT_A_ID,
        )


def test_authorization_context_rejects_missing_roles() -> None:
    with pytest.raises(
        ValueError,
        match="at least one role",
    ):
        AuthorizationContext(
            actor_id="keycloak-user-123",
            tenant_id=TENANT_A_ID,
        )


def test_legacy_role_property_rejects_multi_role_context() -> None:
    context = AuthorizationContext(
        actor_id="keycloak-user-123",
        roles=frozenset(
            {
                Role.EMPLOYEE,
                Role.GROUP_ADMIN,
            }
        ),
        tenant_id=TENANT_A_ID,
    )

    with pytest.raises(
        ValueError,
        match="multiple roles",
    ):
        _ = context.role
