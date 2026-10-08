from __future__ import annotations

from unittest.mock import (
    AsyncMock,
    MagicMock,
)
from uuid import uuid4

import pytest
from fastapi import HTTPException, Request
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.human_context import (
    HumanConversationRequestContext,
)
from app.api.v1.audit import _require_audit_read
from app.auth.id_token import HumanPrincipal
from app.authorization.context import AuthorizationContext
from app.authorization.conversation import (
    ConversationActorContext,
)
from app.authorization.roles import Role
from app.repositories.audit_query import (
    BusinessAuditQueryRepository,
    SecurityAccessQueryRepository,
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
            "path": "/api/v1/audit/business",
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 50000),
            "server": (
                "tenant-a.example.com",
                443,
            ),
            "scheme": "https",
            "app": MagicMock(),
        }
    )


def _context(
    role: Role,
) -> HumanConversationRequestContext:
    tenant_id = uuid4()

    principal = HumanPrincipal(
        subject="user-123",
    )

    tenant = TenantContext(
        tenant_id=tenant_id,
        slug="tenant-a",
        source=TenantContextSource.HOSTNAME,
    )

    authorization = AuthorizationContext(
        actor_id=principal.subject,
        role=role,
        tenant_id=tenant_id,
    )

    actor = ConversationActorContext(
        employee_id=uuid4(),
        member_group_ids=frozenset(),
    )

    return HumanConversationRequestContext(
        principal=principal,
        tenant=tenant,
        authorization=authorization,
        actor=actor,
    )


@pytest.mark.asyncio
async def test_business_audit_query_is_tenant_scoped() -> None:
    tenant_id = uuid4()

    result = MagicMock()
    result.all.return_value = []

    session = AsyncMock(
        spec=AsyncSession,
    )
    session.scalars.return_value = result

    repository = BusinessAuditQueryRepository(
        session=session,
        tenant_id=tenant_id,
    )

    assert await repository.list_events() == []

    statement = session.scalars.await_args.args[0]

    compiled = str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={
                "literal_binds": True,
            },
        )
    )

    assert "business_audit_logs.tenant_id" in compiled
    assert str(tenant_id) in compiled


@pytest.mark.asyncio
async def test_security_access_query_is_tenant_scoped() -> None:
    tenant_id = uuid4()

    result = MagicMock()
    result.all.return_value = []

    session = AsyncMock(
        spec=AsyncSession,
    )
    session.scalars.return_value = result

    repository = SecurityAccessQueryRepository(
        session=session,
        tenant_id=tenant_id,
    )

    assert await repository.list_events() == []

    statement = session.scalars.await_args.args[0]

    compiled = str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={
                "literal_binds": True,
            },
        )
    )

    assert "security_access_logs.tenant_id" in compiled
    assert str(tenant_id) in compiled


@pytest.mark.asyncio
async def test_tenant_admin_can_read_audit() -> None:
    await _require_audit_read(
        request=_request(),
        request_context=_context(
            Role.TENANT_ADMIN,
        ),
    )


@pytest.mark.asyncio
async def test_employee_cannot_read_audit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writer = AsyncMock()

    monkeypatch.setattr(
        "app.api.v1.audit.record_security_access",
        writer,
    )

    with pytest.raises(
        HTTPException
    ) as exc_info:
        await _require_audit_read(
            request=_request(),
            request_context=_context(
                Role.EMPLOYEE,
            ),
        )

    assert exc_info.value.status_code == 403

    writer.assert_awaited_once()

    assert (
        writer.await_args.kwargs["reason_code"]
        == "audit_read_not_allowed"
    )
