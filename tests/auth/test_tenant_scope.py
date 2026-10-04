from uuid import UUID

import pytest

from app.auth.exceptions import TenantIsolationError
from app.auth.permissions import Permission
from app.auth.principals import IntegrationPrincipal
from app.auth.tenant_scope import (
    require_integration_tenant,
    require_resource_tenant,
)
from app.tenants.context import (
    TenantContext,
    TenantContextSource,
)

TENANT_A = UUID("00000000-0000-0000-0000-000000000101")

TENANT_B = UUID("00000000-0000-0000-0000-000000000102")


def test_resource_in_same_tenant_is_allowed() -> None:
    context = TenantContext(
        tenant_id=TENANT_A,
        slug="tenant-a",
        source=TenantContextSource.AUTHENTICATED_SESSION,
    )

    require_resource_tenant(
        context,
        TENANT_A,
    )


def test_cross_tenant_resource_is_rejected() -> None:
    context = TenantContext(
        tenant_id=TENANT_A,
        slug="tenant-a",
        source=TenantContextSource.AUTHENTICATED_SESSION,
    )

    with pytest.raises(TenantIsolationError) as exc_info:
        require_resource_tenant(
            context,
            TENANT_B,
        )

    assert exc_info.value.code == "TENANT_ISOLATION_VIOLATION"


def test_integration_matching_tenant_is_allowed() -> None:
    principal = IntegrationPrincipal(
        integration_id=UUID("00000000-0000-0000-0000-000000000201"),
        tenant_id=TENANT_A,
        client_id="odoo-tenant-a",
        provider="odoo",
        permissions=frozenset(
            {
                Permission.CONVERSATION_READ,
            }
        ),
    )

    context = TenantContext(
        tenant_id=TENANT_A,
        slug="tenant-a",
        source=TenantContextSource.INTEGRATION,
    )

    require_integration_tenant(
        principal,
        context,
    )


def test_integration_cross_tenant_context_is_rejected() -> None:
    principal = IntegrationPrincipal(
        integration_id=UUID("00000000-0000-0000-0000-000000000201"),
        tenant_id=TENANT_A,
        client_id="odoo-tenant-a",
        provider="odoo",
        permissions=frozenset(
            {
                Permission.CONVERSATION_READ,
            }
        ),
    )

    context = TenantContext(
        tenant_id=TENANT_B,
        slug="tenant-b",
        source=TenantContextSource.INTEGRATION,
    )

    with pytest.raises(TenantIsolationError):
        require_integration_tenant(
            principal,
            context,
        )
