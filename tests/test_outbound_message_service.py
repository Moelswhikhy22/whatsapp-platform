from __future__ import annotations

from datetime import (
    UTC,
    datetime,
    timedelta,
)
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

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
from app.db.models.group import Group
from app.db.models.message import (
    MessageStatus,
)
from app.db.models.message_idempotency_key import (
    MessageIdempotencyKey,
)
from app.repositories.outbound_message import (
    OutboundMessageRepository,
)
from app.repositories.outbox_event import (
    OutboxEventRepository,
)
from app.services.outbound_message import (
    IdempotencyKeyConflictError,
    MetaMessagingWindowClosedError,
    OutboundMessageNotAllowedError,
    OutboundMessageService,
)


def _context(
    *,
    tenant_id,
    employee_id,
    group_id,
):
    return (
        AuthorizationContext(
            actor_id="keycloak-user",
            role=Role.EMPLOYEE,
            tenant_id=tenant_id,
        ),
        ConversationActorContext(
            employee_id=employee_id,
            member_group_ids=frozenset(
                {
                    group_id,
                }
            ),
        ),
    )


@pytest.mark.asyncio
async def test_owner_can_create_pending_text_and_outbox() -> None:
    tenant_id = uuid4()
    employee_id = uuid4()
    group_id = uuid4()

    repository = AsyncMock(spec=OutboundMessageRepository)

    outbox = AsyncMock(spec=OutboxEventRepository)

    conversation = Conversation(
        id=uuid4(),
        tenant_id=tenant_id,
        whatsapp_number_id=uuid4(),
        customer_contact_id=uuid4(),
        group_id=group_id,
        state=ConversationState.CLAIMED,
        responsible_employee_id=(employee_id),
    )

    group = Group(
        id=group_id,
        tenant_id=tenant_id,
        name="Sales",
        active=True,
        allow_non_owner_employee_send=False,
    )

    repository.get_conversation.return_value = conversation

    repository.get_active_group.return_value = group

    repository.last_customer_message_at.return_value = datetime.now(UTC) - timedelta(hours=1)

    repository.try_claim_idempotency_key.return_value = uuid4()

    from app.db.models.message import Message

    pending = Message(
        id=uuid4(),
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        direction="outbound",
        message_type="text",
        body_text="Hello",
        actual_actor_id=employee_id,
        status=MessageStatus.PENDING,
    )

    repository.add_pending_text_message.return_value = pending

    context, actor = _context(
        tenant_id=tenant_id,
        employee_id=employee_id,
        group_id=group_id,
    )

    service = OutboundMessageService(
        repository=repository,
        outbox_repository=outbox,
    )

    result = await service.send_text(
        conversation_id=conversation.id,
        body_text="Hello",
        context=context,
        actor=actor,
        idempotency_key="request-123",
    )

    assert result.message.status is MessageStatus.PENDING

    assert result.idempotent_replay is False

    repository.bind_idempotency_message.assert_awaited_once()

    outbox.add_event.assert_called_once()

    call = outbox.add_event.call_args

    assert call.kwargs["event_type"] == "meta.outbound.send"


@pytest.mark.asyncio
async def test_non_owner_employee_is_denied() -> None:
    tenant_id = uuid4()
    owner_id = uuid4()
    employee_id = uuid4()
    group_id = uuid4()

    repository = AsyncMock(spec=OutboundMessageRepository)

    outbox = AsyncMock(spec=OutboxEventRepository)

    repository.get_conversation.return_value = Conversation(
        id=uuid4(),
        tenant_id=tenant_id,
        whatsapp_number_id=uuid4(),
        customer_contact_id=uuid4(),
        group_id=group_id,
        state=ConversationState.CLAIMED,
        responsible_employee_id=owner_id,
    )

    repository.get_active_group.return_value = Group(
        id=group_id,
        tenant_id=tenant_id,
        name="Sales",
        active=True,
        allow_non_owner_employee_send=False,
    )

    context, actor = _context(
        tenant_id=tenant_id,
        employee_id=employee_id,
        group_id=group_id,
    )

    service = OutboundMessageService(
        repository=repository,
        outbox_repository=outbox,
    )

    with pytest.raises(OutboundMessageNotAllowedError):
        await service.send_text(
            conversation_id=(repository.get_conversation.return_value.id),
            body_text="No",
            context=context,
            actor=actor,
            idempotency_key=None,
        )

    repository.add_pending_text_message.assert_not_called()


@pytest.mark.asyncio
async def test_closed_window_rejects_free_text() -> None:
    tenant_id = uuid4()
    employee_id = uuid4()
    group_id = uuid4()

    repository = AsyncMock(spec=OutboundMessageRepository)

    outbox = AsyncMock(spec=OutboxEventRepository)

    conversation = Conversation(
        id=uuid4(),
        tenant_id=tenant_id,
        whatsapp_number_id=uuid4(),
        customer_contact_id=uuid4(),
        group_id=group_id,
        state=ConversationState.CLAIMED,
        responsible_employee_id=(employee_id),
    )

    repository.get_conversation.return_value = conversation

    repository.get_active_group.return_value = Group(
        id=group_id,
        tenant_id=tenant_id,
        name="Sales",
        active=True,
        allow_non_owner_employee_send=False,
    )

    repository.last_customer_message_at.return_value = datetime.now(UTC) - timedelta(hours=25)

    context, actor = _context(
        tenant_id=tenant_id,
        employee_id=employee_id,
        group_id=group_id,
    )

    service = OutboundMessageService(
        repository=repository,
        outbox_repository=outbox,
    )

    with pytest.raises(MetaMessagingWindowClosedError):
        await service.send_text(
            conversation_id=conversation.id,
            body_text="Hello",
            context=context,
            actor=actor,
            idempotency_key=None,
        )

    repository.add_pending_text_message.assert_not_called()


@pytest.mark.asyncio
async def test_same_idempotency_key_returns_existing_message() -> None:
    tenant_id = uuid4()
    employee_id = uuid4()
    group_id = uuid4()
    message_id = uuid4()

    repository = AsyncMock(spec=OutboundMessageRepository)

    outbox = AsyncMock(spec=OutboxEventRepository)

    conversation = Conversation(
        id=uuid4(),
        tenant_id=tenant_id,
        whatsapp_number_id=uuid4(),
        customer_contact_id=uuid4(),
        group_id=group_id,
        state=ConversationState.CLAIMED,
        responsible_employee_id=employee_id,
    )

    repository.get_conversation.return_value = conversation

    repository.get_active_group.return_value = Group(
        id=group_id,
        tenant_id=tenant_id,
        name="Sales",
        active=True,
        allow_non_owner_employee_send=False,
    )

    repository.last_customer_message_at.return_value = datetime.now(UTC)

    repository.try_claim_idempotency_key.return_value = None

    context, actor = _context(
        tenant_id=tenant_id,
        employee_id=employee_id,
        group_id=group_id,
    )

    service = OutboundMessageService(
        repository=repository,
        outbox_repository=outbox,
    )

    request_hash = service._request_hash(
        conversation_id=conversation.id,
        body_text="Hello",
    )

    repository.get_idempotency_key.return_value = MessageIdempotencyKey(
        id=uuid4(),
        tenant_id=tenant_id,
        actor_id=context.actor_id,
        idempotency_key="same-key",
        request_hash=request_hash,
        message_id=message_id,
    )

    pending = repository.add_pending_text_message.return_value
    pending.id = message_id
    pending.tenant_id = tenant_id
    pending.conversation_id = conversation.id
    pending.status = MessageStatus.PENDING

    repository.get_message.return_value = pending

    result = await service.send_text(
        conversation_id=conversation.id,
        body_text="Hello",
        context=context,
        actor=actor,
        idempotency_key="same-key",
    )

    assert result.idempotent_replay

    repository.add_pending_text_message.assert_not_called()
    outbox.add_event.assert_not_called()


@pytest.mark.asyncio
async def test_reusing_key_for_different_body_is_conflict() -> None:
    tenant_id = uuid4()
    employee_id = uuid4()
    group_id = uuid4()

    repository = AsyncMock(spec=OutboundMessageRepository)

    outbox = AsyncMock(spec=OutboxEventRepository)

    conversation = Conversation(
        id=uuid4(),
        tenant_id=tenant_id,
        whatsapp_number_id=uuid4(),
        customer_contact_id=uuid4(),
        group_id=group_id,
        state=ConversationState.CLAIMED,
        responsible_employee_id=employee_id,
    )

    repository.get_conversation.return_value = conversation

    repository.get_active_group.return_value = Group(
        id=group_id,
        tenant_id=tenant_id,
        name="Sales",
        active=True,
        allow_non_owner_employee_send=False,
    )

    repository.last_customer_message_at.return_value = datetime.now(UTC)

    repository.try_claim_idempotency_key.return_value = None

    repository.get_idempotency_key.return_value = MessageIdempotencyKey(
        id=uuid4(),
        tenant_id=tenant_id,
        actor_id="keycloak-user",
        idempotency_key="same",
        request_hash="different-hash",
        message_id=uuid4(),
    )

    context, actor = _context(
        tenant_id=tenant_id,
        employee_id=employee_id,
        group_id=group_id,
    )

    service = OutboundMessageService(
        repository=repository,
        outbox_repository=outbox,
    )

    with pytest.raises(IdempotencyKeyConflictError):
        await service.send_text(
            conversation_id=conversation.id,
            body_text="new body",
            context=context,
            actor=actor,
            idempotency_key="same",
        )
