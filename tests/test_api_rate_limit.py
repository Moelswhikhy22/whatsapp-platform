from __future__ import annotations

from unittest.mock import (
    AsyncMock,
    MagicMock,
)
from uuid import uuid4

import pytest
from fastapi import HTTPException, Request

from app.api.rate_limits import (
    MESSAGE_SEND_RATE_LIMIT,
    _enforce_human_tenant_policy,
)
from app.api.dependencies.human_context import (
    HumanConversationRequestContext,
)
from app.auth.id_token import HumanPrincipal
from app.authorization.context import (
    AuthorizationContext,
)
from app.authorization.conversation import (
    ConversationActorContext,
)
from app.authorization.roles import Role
from app.rate_limit import RateLimitDecision
from app.tenants.context import (
    TenantContext,
    TenantContextSource,
)


def _context() -> HumanConversationRequestContext:
    tenant_id = uuid4()

    principal = HumanPrincipal(
        subject="user-123",
    )

    return HumanConversationRequestContext(
        principal=principal,
        tenant=TenantContext(
            tenant_id=tenant_id,
            slug="tenant-a",
            source=TenantContextSource.HOSTNAME,
        ),
        authorization=AuthorizationContext(
            actor_id=principal.subject,
            role=Role.EMPLOYEE,
            tenant_id=tenant_id,
        ),
        actor=ConversationActorContext(
            employee_id=uuid4(),
            member_group_ids=frozenset(),
        ),
    )


def _request() -> Request:
    app = MagicMock()
    app.state.redis = MagicMock()

    return Request(
        {
            "type": "http",
            "method": "POST",
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
            "app": app,
        }
    )


@pytest.mark.asyncio
async def test_api_rate_limit_returns_429_when_exceeded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    limiter_check = AsyncMock(
        return_value=RateLimitDecision(
            allowed=False,
            limit=60,
            remaining=0,
            retry_after_seconds=12,
        )
    )

    writer = AsyncMock()

    monkeypatch.setattr(
        "app.api.rate_limits.FixedWindowRateLimiter.check",
        limiter_check,
    )
    monkeypatch.setattr(
        "app.api.rate_limits.record_security_access",
        writer,
    )

    with pytest.raises(HTTPException) as exc_info:
        await _enforce_human_tenant_policy(
            request=_request(),
            request_context=_context(),
            policy=MESSAGE_SEND_RATE_LIMIT,
        )

    assert exc_info.value.status_code == 429
    assert exc_info.value.headers["Retry-After"] == "12"
    writer.assert_awaited_once()
