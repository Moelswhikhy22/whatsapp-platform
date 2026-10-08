from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import (
    AsyncMock,
    MagicMock,
)
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)
from starlette.requests import Request

import app.api.dependencies.webhook_context as module
from app.api.dependencies.integration_context import (
    IntegrationRequestContext,
    WEBHOOK_MANAGE_SCOPE,
)
from app.auth.id_token import (
    HumanPrincipal,
)
from app.auth.service_token import (
    ServicePrincipal,
)
from app.authorization.context import (
    AuthorizationContext,
)
from app.authorization.roles import (
    Role,
)
from app.db.models.integration import (
    Integration,
)
from app.tenants.context import (
    TenantContext,
    TenantContextSource,
)


def _request(
    *,
    authorization: str | None = None,
) -> Request:
    headers: list[tuple[bytes, bytes]] = []

    if authorization is not None:
        headers.append(
            (
                b"authorization",
                authorization.encode(),
            )
        )

    return Request(
        {
            "type": "http",
            "method": "GET",
            "scheme": "https",
            "path": ("/api/v1/webhooks"),
            "raw_path": (b"/api/v1/webhooks"),
            "query_string": b"",
            "headers": headers,
            "client": (
                "127.0.0.1",
                12345,
            ),
            "server": (
                "tenant-a.example.com",
                443,
            ),
        }
    )


@pytest.mark.asyncio
async def test_bearer_request_uses_integration_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = uuid4()

    principal = ServicePrincipal(
        client_id=("tenant-a-odoo"),
        subject=("service-account-tenant-a-odoo"),
        scopes=frozenset(
            {
                "whatsapp-platform-api-access",
                WEBHOOK_MANAGE_SCOPE,
            }
        ),
    )

    tenant = TenantContext(
        tenant_id=tenant_id,
        slug="tenant-a",
        source=(TenantContextSource.INTEGRATION),
    )

    authorization = AuthorizationContext(
        actor_id=(principal.client_id),
        role=Role.INTEGRATION,
        tenant_id=tenant_id,
    )

    integration = MagicMock(spec=Integration)

    integration_context = IntegrationRequestContext(
        principal=principal,
        integration=integration,
        tenant=tenant,
        authorization=authorization,
    )

    service_principal = AsyncMock(return_value=principal)

    integration_resolver = AsyncMock(return_value=(integration_context))

    human_principal = AsyncMock()

    monkeypatch.setattr(
        module,
        "require_service_principal",
        service_principal,
    )

    monkeypatch.setattr(
        module,
        ("require_webhook_manage_integration_request_context"),
        integration_resolver,
    )

    monkeypatch.setattr(
        module,
        "require_human_principal",
        human_principal,
    )

    session = AsyncMock(spec=AsyncSession)

    result = await module.require_webhook_request_context(
        request=_request(authorization=("Bearer test-token")),
        session=session,
    )

    assert result.tenant is tenant

    assert result.authorization is authorization

    service_principal.assert_awaited_once()

    integration_resolver.assert_awaited_once_with(
        principal=principal,
        session=session,
    )

    human_principal.assert_not_awaited()


@pytest.mark.asyncio
async def test_no_authorization_header_uses_human_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = uuid4()

    principal = HumanPrincipal(subject="human-user-123")

    tenant = TenantContext(
        tenant_id=tenant_id,
        slug="tenant-a",
        source=(TenantContextSource.AUTHENTICATED_SESSION),
    )

    authorization = AuthorizationContext(
        actor_id=(principal.subject),
        role=Role.TENANT_ADMIN,
        tenant_id=tenant_id,
    )

    human_principal = AsyncMock(return_value=principal)

    human_tenant = AsyncMock(return_value=tenant)

    resolver = MagicMock()

    resolver.resolve = AsyncMock(return_value=(SimpleNamespace(context=authorization)))

    resolver_factory = MagicMock(return_value=resolver)

    service_principal = AsyncMock()

    monkeypatch.setattr(
        module,
        "require_human_principal",
        human_principal,
    )

    monkeypatch.setattr(
        module,
        "require_human_tenant_context",
        human_tenant,
    )

    monkeypatch.setattr(
        module,
        "HumanTenantAuthorizationResolver",
        resolver_factory,
    )

    monkeypatch.setattr(
        module,
        "require_service_principal",
        service_principal,
    )

    session = AsyncMock(spec=AsyncSession)

    request = _request()

    result = await module.require_webhook_request_context(
        request=request,
        session=session,
    )

    assert result.tenant is tenant

    assert result.authorization is authorization

    human_principal.assert_awaited_once_with(request)

    human_tenant.assert_awaited_once_with(
        request=request,
        _principal=principal,
        session=session,
    )

    resolver.resolve.assert_awaited_once_with(
        principal=principal,
        tenant_context=tenant,
    )

    service_principal.assert_not_awaited()


@pytest.mark.asyncio
async def test_invalid_authorization_never_falls_back_to_human(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service_principal = AsyncMock(
        side_effect=HTTPException(
            status_code=401,
            detail="Invalid bearer token.",
        )
    )

    human_principal = AsyncMock()

    monkeypatch.setattr(
        module,
        "require_service_principal",
        service_principal,
    )

    monkeypatch.setattr(
        module,
        "require_human_principal",
        human_principal,
    )

    session = AsyncMock(spec=AsyncSession)

    with pytest.raises(HTTPException) as exc_info:
        await module.require_webhook_request_context(
            request=_request(authorization=("Bearer invalid")),
            session=session,
        )

    assert exc_info.value.status_code == 401

    human_principal.assert_not_awaited()


@pytest.mark.asyncio
async def test_human_without_webhook_permission_is_forbidden(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = uuid4()

    principal = HumanPrincipal(subject="employee-123")

    tenant = TenantContext(
        tenant_id=tenant_id,
        slug="tenant-a",
        source=(TenantContextSource.AUTHENTICATED_SESSION),
    )

    authorization = AuthorizationContext(
        actor_id=(principal.subject),
        role=Role.EMPLOYEE,
        tenant_id=tenant_id,
    )

    monkeypatch.setattr(
        module,
        "require_human_principal",
        AsyncMock(return_value=principal),
    )

    monkeypatch.setattr(
        module,
        "require_human_tenant_context",
        AsyncMock(return_value=tenant),
    )

    resolver = MagicMock()

    resolver.resolve = AsyncMock(return_value=(SimpleNamespace(context=authorization)))

    monkeypatch.setattr(
        module,
        "HumanTenantAuthorizationResolver",
        MagicMock(return_value=resolver),
    )

    session = AsyncMock(spec=AsyncSession)

    with pytest.raises(HTTPException) as exc_info:
        await module.require_webhook_request_context(
            request=_request(),
            session=session,
        )

    assert exc_info.value.status_code == 403

    assert exc_info.value.detail["code"] == ("WEBHOOK_MANAGE_FORBIDDEN")


@pytest.mark.asyncio
async def test_integration_without_rbac_permission_is_forbidden(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = uuid4()

    principal = ServicePrincipal(
        client_id="service-client",
        subject="service-account",
        scopes=frozenset(
            {
                WEBHOOK_MANAGE_SCOPE,
            }
        ),
    )

    tenant = TenantContext(
        tenant_id=tenant_id,
        slug="tenant-a",
        source=(TenantContextSource.INTEGRATION),
    )

    # Intentionally use a role without
    # WEBHOOK_MANAGE to prove that JWT
    # scope alone is insufficient.
    authorization = AuthorizationContext(
        actor_id=(principal.client_id),
        role=Role.EMPLOYEE,
        tenant_id=tenant_id,
    )

    monkeypatch.setattr(
        module,
        "require_service_principal",
        AsyncMock(return_value=principal),
    )

    monkeypatch.setattr(
        module,
        ("require_webhook_manage_integration_request_context"),
        AsyncMock(
            return_value=(
                IntegrationRequestContext(
                    principal=principal,
                    integration=MagicMock(spec=Integration),
                    tenant=tenant,
                    authorization=(authorization),
                )
            )
        ),
    )

    session = AsyncMock(spec=AsyncSession)

    with pytest.raises(HTTPException) as exc_info:
        await module.require_webhook_request_context(
            request=_request(authorization=("Bearer test-token")),
            session=session,
        )

    assert exc_info.value.status_code == 403

    assert exc_info.value.detail["code"] == ("WEBHOOK_MANAGE_FORBIDDEN")
