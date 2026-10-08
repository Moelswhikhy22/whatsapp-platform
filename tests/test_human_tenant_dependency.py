from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.human_tenant import (
    require_human_tenant_context,
)
from app.auth.id_token import HumanPrincipal
from app.services.tenant_resolver import (
    TenantNotFoundError,
    TenantResolver,
)
from app.tenants.context import (
    TenantContext,
    TenantContextSource,
)


def _request(
    hostname: str = "tenant-a.example.com",
) -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "https",
            "path": "/api/v1/conversations",
            "raw_path": b"/api/v1/conversations",
            "query_string": b"",
            "headers": [
                (
                    b"host",
                    hostname.encode(),
                ),
            ],
            "client": (
                "127.0.0.1",
                12345,
            ),
            "server": (
                hostname,
                443,
            ),
        }
    )


@pytest.mark.asyncio
async def test_resolves_human_tenant_and_applies_rls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_context = TenantContext(
        tenant_id=uuid4(),
        slug="tenant-a",
        source=TenantContextSource.HOSTNAME,
    )

    resolve = AsyncMock(
        return_value=tenant_context,
    )

    apply_rls = AsyncMock()

    monkeypatch.setattr(
        TenantResolver,
        "resolve_context_by_hostname",
        resolve,
    )

    monkeypatch.setattr(
        "app.api.dependencies.human_tenant.apply_tenant_rls_context",
        apply_rls,
    )

    session = AsyncMock(
        spec=AsyncSession,
    )

    result = await require_human_tenant_context(
        _request(),
        HumanPrincipal(
            subject="keycloak-user-123",
        ),
        session,
    )

    assert result is tenant_context

    resolve.assert_awaited_once_with(
        "tenant-a.example.com",
    )

    apply_rls.assert_awaited_once_with(
        session,
        tenant_context,
    )


@pytest.mark.asyncio
async def test_unknown_hostname_returns_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolve = AsyncMock(
        side_effect=TenantNotFoundError(
            "Tenant not found.",
        ),
    )

    apply_rls = AsyncMock()

    monkeypatch.setattr(
        TenantResolver,
        "resolve_context_by_hostname",
        resolve,
    )

    monkeypatch.setattr(
        "app.api.dependencies.human_tenant.apply_tenant_rls_context",
        apply_rls,
    )

    session = AsyncMock(
        spec=AsyncSession,
    )

    with pytest.raises(HTTPException) as exc_info:
        await require_human_tenant_context(
            _request(
                "unknown.example.com",
            ),
            HumanPrincipal(
                subject="keycloak-user-123",
            ),
            session,
        )

    assert exc_info.value.status_code == 404

    apply_rls.assert_not_awaited()
