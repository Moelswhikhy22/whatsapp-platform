from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.id_token import HumanPrincipal
from app.authorization.roles import Role
from app.services.human_tenant_authorization import (
    HumanTenantAuthorizationResolver,
    HumanTenantMembershipNotFoundError,
    InvalidHumanTenantRoleError,
)
from app.tenants.context import (
    TenantContext,
    TenantContextSource,
)


def _tenant_context() -> TenantContext:
    return TenantContext(
        tenant_id=uuid4(),
        slug="tenant-a",
        source=TenantContextSource.AUTHENTICATED_SESSION,
    )


@pytest.mark.asyncio
async def test_resolver_builds_authorization_context() -> None:
    session = AsyncMock(spec=AsyncSession)

    scalar_result = MagicMock()
    scalar_result.all.return_value = [
        Role.EMPLOYEE.value,
    ]

    session.scalars.return_value = scalar_result

    tenant_context = _tenant_context()

    resolver = HumanTenantAuthorizationResolver(session)

    resolved = await resolver.resolve(
        principal=HumanPrincipal(subject="keycloak-user-123"),
        tenant_context=tenant_context,
    )

    assert resolved.context.actor_id == "keycloak-user-123"
    assert resolved.context.tenant_id == tenant_context.tenant_id

    assert resolved.context.roles == frozenset(
        {
            Role.EMPLOYEE,
        }
    )


@pytest.mark.asyncio
async def test_resolver_preserves_multiple_roles() -> None:
    session = AsyncMock(spec=AsyncSession)

    scalar_result = MagicMock()
    scalar_result.all.return_value = [
        Role.EMPLOYEE.value,
        Role.GROUP_ADMIN.value,
    ]

    session.scalars.return_value = scalar_result

    resolver = HumanTenantAuthorizationResolver(session)

    resolved = await resolver.resolve(
        principal=HumanPrincipal(subject="keycloak-user-123"),
        tenant_context=_tenant_context(),
    )

    assert resolved.context.roles == frozenset(
        {
            Role.EMPLOYEE,
            Role.GROUP_ADMIN,
        }
    )


@pytest.mark.asyncio
async def test_resolver_rejects_missing_membership() -> None:
    session = AsyncMock(spec=AsyncSession)

    scalar_result = MagicMock()
    scalar_result.all.return_value = []

    session.scalars.return_value = scalar_result

    resolver = HumanTenantAuthorizationResolver(session)

    with pytest.raises(HumanTenantMembershipNotFoundError):
        await resolver.resolve(
            principal=HumanPrincipal(subject="keycloak-user-123"),
            tenant_context=_tenant_context(),
        )


@pytest.mark.asyncio
async def test_resolver_rejects_unknown_role() -> None:
    session = AsyncMock(spec=AsyncSession)

    scalar_result = MagicMock()
    scalar_result.all.return_value = [
        "unknown-role",
    ]

    session.scalars.return_value = scalar_result

    resolver = HumanTenantAuthorizationResolver(session)

    with pytest.raises(InvalidHumanTenantRoleError):
        await resolver.resolve(
            principal=HumanPrincipal(subject="keycloak-user-123"),
            tenant_context=_tenant_context(),
        )


@pytest.mark.asyncio
async def test_resolver_rejects_machine_role() -> None:
    session = AsyncMock(spec=AsyncSession)

    scalar_result = MagicMock()
    scalar_result.all.return_value = [
        Role.INTEGRATION.value,
    ]

    session.scalars.return_value = scalar_result

    resolver = HumanTenantAuthorizationResolver(session)

    with pytest.raises(InvalidHumanTenantRoleError):
        await resolver.resolve(
            principal=HumanPrincipal(subject="keycloak-user-123"),
            tenant_context=_tenant_context(),
        )
