from dataclasses import FrozenInstanceError
from uuid import UUID

import pytest

from app.tenants.context import (
    InvalidTenantContextError,
    TenantContext,
    TenantContextSource,
)

TENANT_ID = UUID("00000000-0000-0000-0000-000000000101")


def test_tenant_context_contains_resolved_tenant() -> None:
    context = TenantContext(
        tenant_id=TENANT_ID,
        slug="tenant-a",
        source=TenantContextSource.AUTHENTICATED_SESSION,
    )

    assert context.tenant_id == TENANT_ID
    assert context.slug == "tenant-a"
    assert context.source is TenantContextSource.AUTHENTICATED_SESSION


def test_tenant_context_is_immutable() -> None:
    context = TenantContext(
        tenant_id=TENANT_ID,
        slug="tenant-a",
        source=TenantContextSource.HOSTNAME,
    )

    with pytest.raises(FrozenInstanceError):
        context.tenant_id = UUID(  # type: ignore[misc]
            "00000000-0000-0000-0000-000000000102"
        )


def test_tenant_context_rejects_nil_uuid() -> None:
    with pytest.raises(
        InvalidTenantContextError,
        match="Tenant ID cannot be the nil UUID",
    ):
        TenantContext(
            tenant_id=UUID("00000000-0000-0000-0000-000000000000"),
            slug="tenant-a",
            source=TenantContextSource.INTEGRATION,
        )
