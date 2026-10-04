from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from app.auth.principals import HumanPrincipal
from app.authorization.roles import Role
from app.db.models.tenant_membership import TenantMembership
from app.repositories.tenant_membership import TenantMembershipRepository
from app.services.human_principal_resolver import (
    HumanPrincipalResolver,
    HumanTenantMembershipDeniedError,
)

TENANT_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
SUBJECT = "keycloak-user-123"


def make_membership(
    *,
    role: Role | str,
) -> TenantMembership:
    role_id = role.value if isinstance(role, Role) else role

    return TenantMembership(
        tenant_id=TENANT_ID,
        user_id=SUBJECT,
        role_id=role_id,
        active=True,
    )


@pytest.mark.asyncio
async def test_resolves_active_employee_membership() -> None:
    repository = AsyncMock(spec=TenantMembershipRepository)

    repository.list_active_for_user.return_value = [
        make_membership(role=Role.EMPLOYEE),
    ]

    resolver = HumanPrincipalResolver(repository)

    principal = await resolver.resolve(
        subject=SUBJECT,
    )

    assert isinstance(principal, HumanPrincipal)
    assert principal.subject == SUBJECT
    assert principal.roles == frozenset(
        {
            Role.EMPLOYEE,
        }
    )

    repository.list_active_for_user.assert_awaited_once_with(
        SUBJECT,
    )


@pytest.mark.asyncio
async def test_resolves_multiple_active_tenant_roles() -> None:
    repository = AsyncMock(spec=TenantMembershipRepository)

    repository.list_active_for_user.return_value = [
        make_membership(role=Role.EMPLOYEE),
        make_membership(role=Role.GROUP_ADMIN),
    ]

    resolver = HumanPrincipalResolver(repository)

    principal = await resolver.resolve(
        subject=SUBJECT,
    )

    assert principal.roles == frozenset(
        {
            Role.EMPLOYEE,
            Role.GROUP_ADMIN,
        }
    )


@pytest.mark.asyncio
async def test_rejects_user_without_active_membership() -> None:
    repository = AsyncMock(spec=TenantMembershipRepository)

    repository.list_active_for_user.return_value = []

    resolver = HumanPrincipalResolver(repository)

    with pytest.raises(
        HumanTenantMembershipDeniedError,
        match="No active tenant membership",
    ):
        await resolver.resolve(
            subject=SUBJECT,
        )


@pytest.mark.asyncio
async def test_rejects_unknown_membership_role() -> None:
    repository = AsyncMock(spec=TenantMembershipRepository)

    repository.list_active_for_user.return_value = [
        make_membership(role="unknown_role"),
    ]

    resolver = HumanPrincipalResolver(repository)

    with pytest.raises(
        HumanTenantMembershipDeniedError,
        match="Invalid tenant membership role",
    ):
        await resolver.resolve(
            subject=SUBJECT,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role",
    [
        Role.PLATFORM_ADMIN,
        Role.INTEGRATION,
    ],
)
async def test_rejects_roles_that_cannot_come_from_tenant_membership(
    role: Role,
) -> None:
    repository = AsyncMock(spec=TenantMembershipRepository)

    repository.list_active_for_user.return_value = [
        make_membership(role=role),
    ]

    resolver = HumanPrincipalResolver(repository)

    with pytest.raises(
        HumanTenantMembershipDeniedError,
        match="Invalid tenant membership role",
    ):
        await resolver.resolve(
            subject=SUBJECT,
        )


@pytest.mark.asyncio
async def test_rejects_empty_subject_before_repository_lookup() -> None:
    repository = AsyncMock(spec=TenantMembershipRepository)

    resolver = HumanPrincipalResolver(repository)

    with pytest.raises(
        ValueError,
        match="subject must not be empty",
    ):
        await resolver.resolve(
            subject="   ",
        )

    repository.list_active_for_user.assert_not_awaited()
