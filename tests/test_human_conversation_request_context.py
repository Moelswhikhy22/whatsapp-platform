from __future__ import annotations

from unittest.mock import (
    AsyncMock,
    MagicMock,
)
from uuid import uuid4
import pytest
from fastapi import (
    HTTPException,
    Request,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.human_context import (
    require_human_conversation_request_context,
)
from app.auth.id_token import HumanPrincipal
from app.authorization.context import AuthorizationContext
from app.authorization.conversation import (
    ConversationActorContext,
)
from app.authorization.roles import Role
from app.services.human_conversation_actor import (
    HumanConversationActorResolver,
)
from app.services.human_tenant_authorization import (
    HumanTenantAuthorization,
    HumanTenantAuthorizationResolver,
    HumanTenantMembershipNotFoundError,
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
async def test_builds_trusted_human_conversation_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = uuid4()
    employee_id = uuid4()
    group_id = uuid4()

    principal = HumanPrincipal(
        subject="keycloak-user-123",
    )

    tenant = TenantContext(
        tenant_id=tenant_id,
        slug="tenant-a",
        source=TenantContextSource.HOSTNAME,
    )

    authorization = AuthorizationContext(
        actor_id=principal.subject,
        tenant_id=tenant_id,
        roles=frozenset(
            {
                Role.EMPLOYEE,
            }
        ),
    )

    actor = ConversationActorContext(
        employee_id=employee_id,
        member_group_ids=frozenset(
            {
                group_id,
            }
        ),
    )

    resolve_authorization = AsyncMock(
        return_value=HumanTenantAuthorization(
            context=authorization,
        ),
    )

    resolve_actor = AsyncMock(
        return_value=actor,
    )

    monkeypatch.setattr(
        HumanTenantAuthorizationResolver,
        "resolve",
        resolve_authorization,
    )

    monkeypatch.setattr(
        HumanConversationActorResolver,
        "resolve",
        resolve_actor,
    )

    session = AsyncMock(
        spec=AsyncSession,
    )
    session.add = MagicMock()

    result = await require_human_conversation_request_context(
        request=_request(),
        principal=principal,
        tenant=tenant,
        session=session,
    )

    assert result.principal is principal
    assert result.tenant is tenant
    assert result.authorization is authorization
    assert result.actor is actor

    resolve_authorization.assert_awaited_once_with(
        principal=principal,
        tenant_context=tenant,
    )

    resolve_actor.assert_awaited_once_with(
        subject=principal.subject,
    )


@pytest.mark.asyncio
async def test_missing_tenant_membership_returns_403(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    principal = HumanPrincipal(
        subject="keycloak-user-123",
    )

    tenant = TenantContext(
        tenant_id=uuid4(),
        slug="tenant-a",
        source=TenantContextSource.HOSTNAME,
    )

    resolve_authorization = AsyncMock(
        side_effect=HumanTenantMembershipNotFoundError(
            "No membership.",
        ),
    )

    resolve_actor = AsyncMock()

    monkeypatch.setattr(
        HumanTenantAuthorizationResolver,
        "resolve",
        resolve_authorization,
    )

    monkeypatch.setattr(
        HumanConversationActorResolver,
        "resolve",
        resolve_actor,
    )

    session = AsyncMock(
        spec=AsyncSession,
    )
    session.add = MagicMock()

    with pytest.raises(HTTPException) as exc_info:
        await require_human_conversation_request_context(
            request=_request(),
            principal=principal,
            tenant=tenant,
            session=session,
        )
    assert exc_info.value.status_code == 403

    resolve_actor.assert_not_awaited()
