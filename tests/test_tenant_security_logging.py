from __future__ import annotations

from unittest.mock import (
    AsyncMock,
    MagicMock,
    patch,
)
from uuid import uuid4

import pytest
from fastapi import (
    HTTPException,
    Request,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from app.api.dependencies.human_context import (
    require_human_conversation_request_context,
)
from app.api.dependencies.human_tenant import (
    require_human_tenant_context,
)
from app.auth.id_token import HumanPrincipal
from app.db.models.security_access_log import (
    SecurityAccessOutcome,
    SecurityPrincipalType,
)
from app.services.human_tenant_authorization import (
    HumanTenantMembershipNotFoundError,
    InvalidHumanTenantRoleError,
)
from app.services.tenant_resolver import (
    TenantResolutionConflictError,
    TenantUnavailableError,
)
from app.tenants.context import (
    TenantContext,
    TenantContextSource,
)


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/test",
            "query_string": b"",
            "headers": [],
            "client": (
                "127.0.0.1",
                50000,
            ),
            "server": (
                "tenant-a.example.com",
                443,
            ),
            "scheme": "https",
            "app": MagicMock(),
        }
    )


@pytest.mark.asyncio
async def test_unavailable_tenant_is_security_denial() -> None:
    request = _request()

    principal = HumanPrincipal(
        subject="user-123",
    )

    session = MagicMock(
        spec=AsyncSession,
    )

    resolver = MagicMock()

    resolver.resolve_context_by_hostname = AsyncMock(
        side_effect=TenantUnavailableError(
            tenant_id=uuid4(),
            status="suspended",
        )
    )
    security_writer = AsyncMock()

    with (
        patch(
            ("app.api.dependencies.human_tenant.TenantResolver"),
            return_value=resolver,
        ),
        patch(
            ("app.api.dependencies.human_tenant.record_security_access"),
            security_writer,
        ),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await require_human_tenant_context(
                request=request,
                _principal=principal,
                session=session,
            )

    assert exc_info.value.status_code == 403

    call = security_writer.await_args

    assert call.kwargs["principal_type"] is SecurityPrincipalType.HUMAN

    assert call.kwargs["principal_id"] == "user-123"

    assert call.kwargs["outcome"] is SecurityAccessOutcome.DENIED

    assert call.kwargs["reason_code"] == "tenant_unavailable"


@pytest.mark.asyncio
async def test_tenant_resolution_conflict_is_security_failure() -> None:
    request = _request()

    principal = HumanPrincipal(
        subject="user-123",
    )

    session = MagicMock(
        spec=AsyncSession,
    )

    resolver = MagicMock()

    resolver.resolve_context_by_hostname = AsyncMock(side_effect=(TenantResolutionConflictError))

    security_writer = AsyncMock()

    with (
        patch(
            ("app.api.dependencies.human_tenant.TenantResolver"),
            return_value=resolver,
        ),
        patch(
            ("app.api.dependencies.human_tenant.record_security_access"),
            security_writer,
        ),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await require_human_tenant_context(
                request=request,
                _principal=principal,
                session=session,
            )

    assert exc_info.value.status_code == 500

    call = security_writer.await_args

    assert call.kwargs["outcome"] is SecurityAccessOutcome.FAILURE

    assert call.kwargs["reason_code"] == "tenant_resolution_conflict"


@pytest.mark.asyncio
async def test_missing_tenant_membership_is_security_denial() -> None:
    request = _request()

    principal = HumanPrincipal(
        subject="user-123",
    )

    tenant = TenantContext(
        tenant_id=uuid4(),
        slug="tenant-a",
        source=TenantContextSource.HOSTNAME,
    )

    session = MagicMock(
        spec=AsyncSession,
    )

    resolver = MagicMock()

    resolver.resolve = AsyncMock(side_effect=(HumanTenantMembershipNotFoundError))

    security_writer = AsyncMock()

    with (
        patch(
            ("app.api.dependencies.human_context.HumanTenantAuthorizationResolver"),
            return_value=resolver,
        ),
        patch(
            ("app.api.dependencies.human_context.record_security_access"),
            security_writer,
        ),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await require_human_conversation_request_context(
                request=request,
                principal=principal,
                tenant=tenant,
                session=session,
            )

    assert exc_info.value.status_code == 403

    call = security_writer.await_args

    assert call.kwargs["tenant_id"] == tenant.tenant_id

    assert call.kwargs["resource_type"] == "tenant"

    assert call.kwargs["resource_id"] == str(tenant.tenant_id)

    assert call.kwargs["reason_code"] == "tenant_membership_not_found"


@pytest.mark.asyncio
async def test_invalid_tenant_role_is_security_denial() -> None:
    request = _request()

    principal = HumanPrincipal(
        subject="user-123",
    )

    tenant = TenantContext(
        tenant_id=uuid4(),
        slug="tenant-a",
        source=TenantContextSource.HOSTNAME,
    )

    session = MagicMock(
        spec=AsyncSession,
    )

    resolver = MagicMock()

    resolver.resolve = AsyncMock(side_effect=(InvalidHumanTenantRoleError))

    security_writer = AsyncMock()

    with (
        patch(
            ("app.api.dependencies.human_context.HumanTenantAuthorizationResolver"),
            return_value=resolver,
        ),
        patch(
            ("app.api.dependencies.human_context.record_security_access"),
            security_writer,
        ),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await require_human_conversation_request_context(
                request=request,
                principal=principal,
                tenant=tenant,
                session=session,
            )

    assert exc_info.value.status_code == 403

    call = security_writer.await_args

    assert call.kwargs["outcome"] is SecurityAccessOutcome.DENIED

    assert call.kwargs["reason_code"] == "invalid_tenant_role"
