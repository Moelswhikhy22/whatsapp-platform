from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.tenant import Tenant, TenantStatus
from app.services.tenant_resolver import (
    InvalidTenantHostnameError,
    TenantNotFoundError,
    TenantResolutionConflictError,
    TenantResolver,
    TenantUnavailableError,
    normalize_tenant_hostname,
)


def test_normalize_tenant_hostname() -> None:
    assert normalize_tenant_hostname(" Support.Example.COM. ") == "support.example.com"


def test_normalize_tenant_hostname_rejects_empty() -> None:
    with pytest.raises(InvalidTenantHostnameError):
        normalize_tenant_hostname("   ")


def test_normalize_tenant_hostname_rejects_url() -> None:
    with pytest.raises(InvalidTenantHostnameError):
        normalize_tenant_hostname("https://example.com")


@pytest.mark.asyncio
async def test_resolver_returns_active_tenant() -> None:
    session = AsyncMock(spec=AsyncSession)

    tenant = Tenant(
        id=uuid4(),
        name="Example",
        slug="example",
        status=TenantStatus.ACTIVE,
    )

    scalar_result = MagicMock()
    scalar_result.all.return_value = [tenant]

    session.scalars.return_value = scalar_result

    resolver = TenantResolver(session)

    resolved = await resolver.resolve_by_hostname("example.com")

    assert resolved is tenant


@pytest.mark.asyncio
async def test_resolver_rejects_unknown_hostname() -> None:
    session = AsyncMock(spec=AsyncSession)

    scalar_result = MagicMock()
    scalar_result.all.return_value = []

    session.scalars.return_value = scalar_result

    resolver = TenantResolver(session)

    with pytest.raises(TenantNotFoundError):
        await resolver.resolve_by_hostname("unknown.example.com")


@pytest.mark.asyncio
async def test_resolver_rejects_suspended_tenant() -> None:
    session = AsyncMock(spec=AsyncSession)

    tenant = Tenant(
        id=uuid4(),
        name="Example",
        slug="example",
        status=TenantStatus.SUSPENDED,
    )

    scalar_result = MagicMock()
    scalar_result.all.return_value = [tenant]

    session.scalars.return_value = scalar_result

    resolver = TenantResolver(session)

    with pytest.raises(TenantUnavailableError):
        await resolver.resolve_by_hostname("example.com")


@pytest.mark.asyncio
async def test_resolver_rejects_disabled_tenant() -> None:
    session = AsyncMock(spec=AsyncSession)

    tenant = Tenant(
        id=uuid4(),
        name="Example",
        slug="example",
        status=TenantStatus.DISABLED,
    )

    scalar_result = MagicMock()
    scalar_result.all.return_value = [tenant]

    session.scalars.return_value = scalar_result

    resolver = TenantResolver(session)

    with pytest.raises(TenantUnavailableError):
        await resolver.resolve_by_hostname("example.com")


@pytest.mark.asyncio
async def test_resolver_rejects_ambiguous_hostname() -> None:
    session = AsyncMock(spec=AsyncSession)

    tenant_a = Tenant(
        id=uuid4(),
        name="Tenant A",
        slug="tenant-a",
        status=TenantStatus.ACTIVE,
    )

    tenant_b = Tenant(
        id=uuid4(),
        name="Tenant B",
        slug="tenant-b",
        status=TenantStatus.ACTIVE,
    )

    scalar_result = MagicMock()
    scalar_result.all.return_value = [
        tenant_a,
        tenant_b,
    ]

    session.scalars.return_value = scalar_result

    resolver = TenantResolver(session)

    with pytest.raises(TenantResolutionConflictError):
        await resolver.resolve_by_hostname("example.com")


@pytest.mark.asyncio
async def test_resolver_creates_tenant_context() -> None:
    session = AsyncMock(spec=AsyncSession)

    tenant_id = uuid4()

    tenant = Tenant(
        id=tenant_id,
        name="Example",
        slug="example",
        status=TenantStatus.ACTIVE,
    )

    scalar_result = MagicMock()
    scalar_result.all.return_value = [tenant]

    session.scalars.return_value = scalar_result

    resolver = TenantResolver(session)

    context = await resolver.resolve_context_by_hostname("example.com")

    assert context.tenant_id == tenant_id
    assert context.slug == "example"
