from dataclasses import FrozenInstanceError
from uuid import uuid4

import pytest

from app.db.models.tenant import Tenant, TenantStatus
from app.tenants.context import (
    InvalidTenantContextError,
    TenantContext,
    TenantContextSource,
)


def test_tenant_context_is_created_from_active_tenant() -> None:
    tenant_id = uuid4()

    tenant = Tenant(
        id=tenant_id,
        name="Example",
        slug="example",
        status=TenantStatus.ACTIVE,
    )

    context = TenantContext.from_tenant(
        tenant,
        source=TenantContextSource.HOSTNAME,
    )

    assert context.tenant_id == tenant_id
    assert context.slug == "example"
    assert context.source is TenantContextSource.HOSTNAME


def test_tenant_context_is_immutable() -> None:
    context = TenantContext(
        tenant_id=uuid4(),
        slug="example",
        source=TenantContextSource.AUTHENTICATED_SESSION,
    )

    with pytest.raises(FrozenInstanceError):
        context.slug = "other"  # type: ignore[misc]


def test_tenant_id_cannot_be_changed() -> None:
    context = TenantContext(
        tenant_id=uuid4(),
        slug="example",
        source=TenantContextSource.AUTHENTICATED_SESSION,
    )

    with pytest.raises(FrozenInstanceError):
        context.tenant_id = uuid4()  # type: ignore[misc]


def test_context_rejects_suspended_tenant() -> None:
    tenant = Tenant(
        id=uuid4(),
        name="Example",
        slug="example",
        status=TenantStatus.SUSPENDED,
    )

    with pytest.raises(InvalidTenantContextError):
        TenantContext.from_tenant(
            tenant,
            source=TenantContextSource.HOSTNAME,
        )


def test_context_rejects_disabled_tenant() -> None:
    tenant = Tenant(
        id=uuid4(),
        name="Example",
        slug="example",
        status=TenantStatus.DISABLED,
    )

    with pytest.raises(InvalidTenantContextError):
        TenantContext.from_tenant(
            tenant,
            source=TenantContextSource.HOSTNAME,
        )


def test_context_rejects_empty_slug() -> None:
    tenant = Tenant(
        id=uuid4(),
        name="Example",
        slug="   ",
        status=TenantStatus.ACTIVE,
    )

    with pytest.raises(InvalidTenantContextError):
        TenantContext.from_tenant(
            tenant,
            source=TenantContextSource.HOSTNAME,
        )
