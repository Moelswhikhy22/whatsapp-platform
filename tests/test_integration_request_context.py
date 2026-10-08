from __future__ import annotations

from unittest.mock import (
    AsyncMock,
)
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from app.api.dependencies.integration_context import (
    WEBHOOK_MANAGE_SCOPE,
    _require_service_scope,
    resolve_integration_request_context,
)
from app.auth.service_token import (
    ServicePrincipal,
)
from app.authorization.roles import (
    Role,
)
from app.db.models.integration import (
    Integration,
    IntegrationProvider,
)
from app.db.models.tenant import (
    Tenant,
    TenantStatus,
)
from app.repositories.integration import (
    ServiceIntegrationIdentityRepository,
)
from app.tenants.context import (
    TenantContextSource,
)


def _principal(
    *,
    scopes: frozenset[str] | None = None,
) -> ServicePrincipal:
    return ServicePrincipal(
        client_id=("tenant-a-odoo"),
        subject=("service-account-tenant-a-odoo"),
        scopes=(
            scopes
            or frozenset(
                {
                    "whatsapp-platform-api-access",
                    WEBHOOK_MANAGE_SCOPE,
                }
            )
        ),
    )


def _integration(
    *,
    tenant_id,
) -> Integration:
    return Integration(
        id=uuid4(),
        tenant_id=tenant_id,
        provider=(IntegrationProvider.ODOO),
        name="Odoo",
        external_account_id=None,
        keycloak_client_id=("tenant-a-odoo"),
        config_json={},
        active=True,
    )


def _tenant(
    *,
    tenant_id,
) -> Tenant:
    return Tenant(
        id=tenant_id,
        name="Tenant A",
        slug="tenant-a",
        status=TenantStatus.ACTIVE,
    )


@pytest.mark.asyncio
async def test_resolves_trusted_integration_request_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = uuid4()

    integration = _integration(tenant_id=tenant_id)

    tenant = _tenant(tenant_id=tenant_id)

    get_integration = AsyncMock(return_value=integration)

    get_tenant = AsyncMock(return_value=tenant)

    monkeypatch.setattr(
        ServiceIntegrationIdentityRepository,
        "get_active_by_keycloak_client_id",
        get_integration,
    )

    monkeypatch.setattr(
        ServiceIntegrationIdentityRepository,
        "get_active_tenant_by_id",
        get_tenant,
    )

    session = AsyncMock(spec=AsyncSession)

    principal = _principal()

    context = await resolve_integration_request_context(
        principal=principal,
        session=session,
    )

    assert context.principal is principal

    assert context.integration is integration

    assert context.tenant.tenant_id == tenant_id

    assert context.tenant.slug == "tenant-a"

    assert context.tenant.source is TenantContextSource.INTEGRATION

    assert context.authorization.actor_id == "tenant-a-odoo"

    assert context.authorization.tenant_id == tenant_id

    assert context.authorization.role is Role.INTEGRATION

    get_integration.assert_awaited_once_with(client_id=("tenant-a-odoo"))

    get_tenant.assert_awaited_once_with(tenant_id=tenant_id)


@pytest.mark.asyncio
async def test_unregistered_service_identity_is_forbidden(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    get_integration = AsyncMock(return_value=None)

    get_tenant = AsyncMock()

    monkeypatch.setattr(
        ServiceIntegrationIdentityRepository,
        "get_active_by_keycloak_client_id",
        get_integration,
    )

    monkeypatch.setattr(
        ServiceIntegrationIdentityRepository,
        "get_active_tenant_by_id",
        get_tenant,
    )

    session = AsyncMock(spec=AsyncSession)

    with pytest.raises(HTTPException) as exc_info:
        await resolve_integration_request_context(
            principal=_principal(),
            session=session,
        )

    assert exc_info.value.status_code == 403

    assert exc_info.value.detail["code"] == ("SERVICE_INTEGRATION_NOT_REGISTERED")

    get_tenant.assert_not_awaited()


@pytest.mark.asyncio
async def test_inactive_or_missing_tenant_is_forbidden(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = uuid4()

    integration = _integration(tenant_id=tenant_id)

    monkeypatch.setattr(
        ServiceIntegrationIdentityRepository,
        "get_active_by_keycloak_client_id",
        AsyncMock(return_value=integration),
    )

    monkeypatch.setattr(
        ServiceIntegrationIdentityRepository,
        "get_active_tenant_by_id",
        AsyncMock(return_value=None),
    )

    session = AsyncMock(spec=AsyncSession)

    with pytest.raises(HTTPException) as exc_info:
        await resolve_integration_request_context(
            principal=_principal(),
            session=session,
        )

    assert exc_info.value.status_code == 403

    assert exc_info.value.detail["code"] == ("SERVICE_INTEGRATION_TENANT_UNAVAILABLE")


def test_webhook_manage_scope_is_accepted() -> None:
    principal = _principal()

    _require_service_scope(
        principal=principal,
        required_scope=(WEBHOOK_MANAGE_SCOPE),
    )


def test_missing_webhook_manage_scope_is_forbidden() -> None:
    principal = _principal(scopes=frozenset({"whatsapp-platform-api-access"}))

    with pytest.raises(HTTPException) as exc_info:
        _require_service_scope(
            principal=principal,
            required_scope=(WEBHOOK_MANAGE_SCOPE),
        )

    assert exc_info.value.status_code == 403

    assert exc_info.value.detail["code"] == "SERVICE_SCOPE_REQUIRED"

    assert exc_info.value.detail["required_scope"] == WEBHOOK_MANAGE_SCOPE

    assert exc_info.value.headers is not None

    assert "insufficient_scope" in (exc_info.value.headers["WWW-Authenticate"])
