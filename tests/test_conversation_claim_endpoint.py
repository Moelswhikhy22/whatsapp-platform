from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import (
    AsyncMock,
    MagicMock,
)
from uuid import uuid4

import pytest
from fastapi import (
    FastAPI,
    HTTPException,
    Request,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.human_context import (
    HumanConversationRequestContext,
)
from app.api.v1.conversations import (
    CONVERSATION_ALREADY_CLAIMED,
    CONVERSATION_CLAIM_NOT_ALLOWED,
    CONVERSATION_NOT_FOUND,
    claim_conversation,
)
from app.api.v1.router import api_router
from app.auth.id_token import HumanPrincipal
from app.authorization.context import (
    AuthorizationContext,
)
from app.authorization.conversation import (
    ConversationActorContext,
)
from app.authorization.roles import Role
from app.db.models.conversation import (
    Conversation,
    ConversationState,
)
from app.db.models.security_access_log import (
    SecurityAccessOutcome,
    SecurityPrincipalType,
)
from app.services.conversation_claim import (
    ConversationAlreadyClaimedError,
    ConversationClaimNotAllowedError,
    ConversationClaimService,
    ConversationNotFoundError,
)
from app.tenants.context import (
    TenantContext,
    TenantContextSource,
)


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": ("/api/v1/conversations/test-conversation/claim"),
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


def _request_context() -> HumanConversationRequestContext:
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
        role=Role.EMPLOYEE,
        tenant_id=tenant_id,
    )

    actor = ConversationActorContext(
        employee_id=employee_id,
        member_group_ids=frozenset(
            {
                group_id,
            }
        ),
    )

    return HumanConversationRequestContext(
        principal=principal,
        tenant=tenant,
        authorization=authorization,
        actor=actor,
    )


def _claimed_conversation(
    context: HumanConversationRequestContext,
) -> Conversation:
    employee_id = context.actor.employee_id

    assert employee_id is not None

    return Conversation(
        id=uuid4(),
        tenant_id=context.tenant.tenant_id,
        whatsapp_number_id=uuid4(),
        customer_contact_id=uuid4(),
        group_id=next(
            iter(
                context.actor.member_group_ids,
            )
        ),
        state=ConversationState.CLAIMED,
        responsible_employee_id=employee_id,
        claimed_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_claim_endpoint_commits_successful_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _request_context()

    claimed = _claimed_conversation(
        context,
    )

    service_claim = AsyncMock(
        return_value=claimed,
    )

    monkeypatch.setattr(
        ConversationClaimService,
        "claim",
        service_claim,
    )

    session = AsyncMock(
        spec=AsyncSession,
    )

    result = await claim_conversation(
        conversation_id=claimed.id,
        request=_request(),
        request_context=context,
        session=session,
    )

    assert result.id == claimed.id

    assert result.state is ConversationState.CLAIMED

    assert result.responsible_employee_id == claimed.responsible_employee_id

    assert result.claimed_at == claimed.claimed_at

    service_claim.assert_awaited_once_with(
        conversation_id=claimed.id,
        context=context.authorization,
        actor=context.actor,
    )

    session.commit.assert_awaited_once()

    session.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_claim_endpoint_returns_404_for_missing_conversation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _request_context()

    service_claim = AsyncMock(
        side_effect=ConversationNotFoundError,
    )

    monkeypatch.setattr(
        ConversationClaimService,
        "claim",
        service_claim,
    )

    session = AsyncMock(
        spec=AsyncSession,
    )

    conversation_id = uuid4()

    with pytest.raises(HTTPException) as exc_info:
        await claim_conversation(
            conversation_id=conversation_id,
            request=_request(),
            request_context=context,
            session=session,
        )

    assert exc_info.value.status_code == 404

    assert exc_info.value.detail == {
        "code": CONVERSATION_NOT_FOUND,
        "message": ("Conversation was not found."),
    }

    session.rollback.assert_awaited_once()

    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_claim_endpoint_returns_403_when_claim_not_allowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _request_context()

    conversation_id = uuid4()

    service_claim = AsyncMock(
        side_effect=(ConversationClaimNotAllowedError),
    )

    security_writer = AsyncMock()

    monkeypatch.setattr(
        ConversationClaimService,
        "claim",
        service_claim,
    )

    monkeypatch.setattr(
        ("app.api.v1.conversations.record_security_access"),
        security_writer,
    )

    session = AsyncMock(
        spec=AsyncSession,
    )

    request = _request()

    with pytest.raises(HTTPException) as exc_info:
        await claim_conversation(
            conversation_id=conversation_id,
            request=request,
            request_context=context,
            session=session,
        )

    assert exc_info.value.status_code == 403

    assert exc_info.value.detail == {
        "code": (CONVERSATION_CLAIM_NOT_ALLOWED),
        "message": ("Conversation cannot be claimed by this actor."),
    }

    session.rollback.assert_awaited_once()

    session.commit.assert_not_awaited()

    security_writer.assert_awaited_once()

    security_call = security_writer.await_args

    assert security_call.kwargs["request"] is request

    assert security_call.kwargs["principal_type"] is SecurityPrincipalType.HUMAN

    assert security_call.kwargs["principal_id"] == context.principal.subject

    assert security_call.kwargs["tenant_id"] == context.tenant.tenant_id

    assert security_call.kwargs["event"] == "authorization.denied"

    assert security_call.kwargs["outcome"] is SecurityAccessOutcome.DENIED

    assert security_call.kwargs["resource_type"] == "conversation"

    assert security_call.kwargs["resource_id"] == str(conversation_id)

    assert security_call.kwargs["reason_code"] == "conversation_claim_not_allowed"


@pytest.mark.asyncio
async def test_claim_endpoint_returns_409_when_atomic_claim_loses_race(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _request_context()

    service_claim = AsyncMock(
        side_effect=(ConversationAlreadyClaimedError),
    )

    monkeypatch.setattr(
        ConversationClaimService,
        "claim",
        service_claim,
    )

    session = AsyncMock(
        spec=AsyncSession,
    )

    conversation_id = uuid4()

    with pytest.raises(HTTPException) as exc_info:
        await claim_conversation(
            conversation_id=conversation_id,
            request=_request(),
            request_context=context,
            session=session,
        )

    assert exc_info.value.status_code == 409

    assert exc_info.value.detail == {
        "code": (CONVERSATION_ALREADY_CLAIMED),
        "message": ("Conversation has already been claimed."),
    }

    session.rollback.assert_awaited_once()

    session.commit.assert_not_awaited()


def test_claim_route_is_registered() -> None:
    app = FastAPI()

    app.include_router(
        api_router,
        prefix="/api/v1",
    )

    openapi = app.openapi()

    path = "/api/v1/conversations/{conversation_id}/claim"

    assert path in openapi["paths"]

    assert "post" in openapi["paths"][path]
