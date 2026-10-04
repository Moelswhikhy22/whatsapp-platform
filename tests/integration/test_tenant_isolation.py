from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.tenant import Tenant
from app.db.models.tenant_domain import TenantDomain
from app.db.models.tenant_membership import TenantMembership
from app.repositories.tenant_domain import (
    TenantDomainRepository,
)
from app.repositories.tenant_membership import (
    TenantMembershipRepository,
)
from app.tenants.context import TenantContext

pytestmark = pytest.mark.integration


async def create_two_tenant_fixture(
    session: AsyncSession,
) -> tuple[
    Tenant,
    Tenant,
    TenantDomain,
    TenantDomain,
    TenantMembership,
    TenantMembership,
]:
    tenant_a = Tenant(
        name="Isolation Tenant A",
        slug="isolation-tenant-a",
    )

    tenant_b = Tenant(
        name="Isolation Tenant B",
        slug="isolation-tenant-b",
    )

    session.add_all(
        [
            tenant_a,
            tenant_b,
        ]
    )

    await session.flush()

    domain_a = TenantDomain(
        tenant_id=tenant_a.id,
        hostname="a.isolation.example.com",
    )

    domain_b = TenantDomain(
        tenant_id=tenant_b.id,
        hostname="b.isolation.example.com",
    )

    membership_a = TenantMembership(
        tenant_id=tenant_a.id,
        user_id="shared-user",
        role_id="employee",
    )

    membership_b = TenantMembership(
        tenant_id=tenant_b.id,
        user_id="shared-user",
        role_id="employee",
    )

    session.add_all(
        [
            domain_a,
            domain_b,
            membership_a,
            membership_b,
        ]
    )

    await session.flush()

    return (
        tenant_a,
        tenant_b,
        domain_a,
        domain_b,
        membership_a,
        membership_b,
    )


@pytest.mark.asyncio
async def test_tenant_cannot_read_other_tenant_domain_by_id(
    integration_session: AsyncSession,
) -> None:
    (
        tenant_a,
        _,
        _,
        domain_b,
        _,
        _,
    ) = await create_two_tenant_fixture(integration_session)

    context_a = TenantContext(
        tenant_id=tenant_a.id,
        slug=tenant_a.slug,
    )

    repository = TenantDomainRepository(
        session=integration_session,
        tenant=context_a,
    )

    result = await repository.get_by_id(domain_b.id)

    assert result is None


@pytest.mark.asyncio
async def test_tenant_can_read_own_domain(
    integration_session: AsyncSession,
) -> None:
    (
        tenant_a,
        _,
        domain_a,
        _,
        _,
        _,
    ) = await create_two_tenant_fixture(integration_session)

    context_a = TenantContext(
        tenant_id=tenant_a.id,
        slug=tenant_a.slug,
    )

    repository = TenantDomainRepository(
        session=integration_session,
        tenant=context_a,
    )

    result = await repository.get_by_id(domain_a.id)

    assert result is not None
    assert result.id == domain_a.id
    assert result.tenant_id == tenant_a.id


@pytest.mark.asyncio
async def test_tenant_domain_list_is_isolated(
    integration_session: AsyncSession,
) -> None:
    (
        tenant_a,
        _,
        domain_a,
        domain_b,
        _,
        _,
    ) = await create_two_tenant_fixture(integration_session)

    context_a = TenantContext(
        tenant_id=tenant_a.id,
        slug=tenant_a.slug,
    )

    repository = TenantDomainRepository(
        session=integration_session,
        tenant=context_a,
    )

    domains = await repository.list_all()

    ids = {domain.id for domain in domains}

    assert domain_a.id in ids
    assert domain_b.id not in ids


@pytest.mark.asyncio
async def test_tenant_cannot_lookup_other_tenant_hostname(
    integration_session: AsyncSession,
) -> None:
    (
        tenant_a,
        _,
        _,
        domain_b,
        _,
        _,
    ) = await create_two_tenant_fixture(integration_session)

    context_a = TenantContext(
        tenant_id=tenant_a.id,
        slug=tenant_a.slug,
    )

    repository = TenantDomainRepository(
        session=integration_session,
        tenant=context_a,
    )

    result = await repository.get_by_hostname(domain_b.hostname)

    assert result is None


@pytest.mark.asyncio
async def test_tenant_cannot_read_other_tenant_membership_by_id(
    integration_session: AsyncSession,
) -> None:
    (
        tenant_a,
        _,
        _,
        _,
        _,
        membership_b,
    ) = await create_two_tenant_fixture(integration_session)

    context_a = TenantContext(
        tenant_id=tenant_a.id,
        slug=tenant_a.slug,
    )

    repository = TenantMembershipRepository(
        session=integration_session,
        tenant=context_a,
    )

    result = await repository.get_by_id(membership_b.id)

    assert result is None


@pytest.mark.asyncio
async def test_membership_lookup_returns_only_current_tenant(
    integration_session: AsyncSession,
) -> None:
    (
        tenant_a,
        _,
        _,
        _,
        membership_a,
        membership_b,
    ) = await create_two_tenant_fixture(integration_session)

    context_a = TenantContext(
        tenant_id=tenant_a.id,
        slug=tenant_a.slug,
    )

    repository = TenantMembershipRepository(
        session=integration_session,
        tenant=context_a,
    )

    memberships = await repository.list_for_user("shared-user")

    ids = {membership.id for membership in memberships}

    assert membership_a.id in ids
    assert membership_b.id not in ids

    assert all(membership.tenant_id == tenant_a.id for membership in memberships)


@pytest.mark.asyncio
async def test_tenant_b_is_also_isolated_from_tenant_a(
    integration_session: AsyncSession,
) -> None:
    (
        _,
        tenant_b,
        domain_a,
        domain_b,
        _,
        _,
    ) = await create_two_tenant_fixture(integration_session)

    context_b = TenantContext(
        tenant_id=tenant_b.id,
        slug=tenant_b.slug,
    )

    repository = TenantDomainRepository(
        session=integration_session,
        tenant=context_b,
    )

    own = await repository.get_by_id(domain_b.id)

    foreign = await repository.get_by_id(domain_a.id)

    assert own is not None
    assert foreign is None
