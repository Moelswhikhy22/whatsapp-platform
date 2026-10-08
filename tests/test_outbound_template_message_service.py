from __future__ import annotations

from unittest.mock import (
    AsyncMock,
    MagicMock,
)
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
    Message,
    MessageDirection,
    MessageStatus,
    MessageType,
)
from app.db.models.template import (
    Template,
    TemplateStatus,
    TemplateType,
)
from app.db.models.whatsapp_number import (
    WhatsAppNumber,
)
from app.repositories.outbound_message import (
    OutboundMessageRepository,
)
from app.repositories.outbox_event import (
    OutboxEventRepository,
)
from app.services.outbound_message import (
    OutboundMessageService,
    OutboundTemplateAccountMismatchError,
    OutboundTemplateNotApprovedError,
)


def _objects():
    tenant_id = uuid4()
    employee_id = uuid4()
    group_id = uuid4()
    integration_id = uuid4()

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

    number = WhatsAppNumber(
        id=conversation.whatsapp_number_id,
        tenant_id=tenant_id,
        integration_id=integration_id,
        meta_phone_number_id="123456",
        display_phone_number=("+201111111111"),
        active=True,
    )

    template = Template(
        id=uuid4(),
        tenant_id=tenant_id,
        template_type=TemplateType.META,
        category="UTILITY",
        name=None,
        body=None,
        variables_json=None,
        active=None,
        meta_template_name=("payment_reminder"),
        language="en_US",
        components_json=[
            {
                "type": "BODY",
                "text": "Hello {{1}}",
            }
        ],
        status=TemplateStatus.APPROVED,
        meta_account_id=integration_id,
        last_synced_at=None,
    )

    context = AuthorizationContext(
        actor_id="keycloak-user",
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

    return (
        conversation,
        group,
        number,
        template,
        context,
        actor,
    )


@pytest.mark.asyncio
async def test_approved_template_creates_pending_message_and_outbox() -> None:
    (
        conversation,
        group,
        number,
        template,
        context,
        actor,
    ) = _objects()

    repository = AsyncMock(spec=OutboundMessageRepository)

    outbox = MagicMock(spec=OutboxEventRepository)

    repository.get_conversation.return_value = conversation
    repository.get_active_group.return_value = group
    repository.get_meta_template.return_value = template
    repository.get_active_whatsapp_number.return_value = number
    repository.try_claim_idempotency_key.return_value = uuid4()

    pending = Message(
        id=uuid4(),
        tenant_id=conversation.tenant_id,
        conversation_id=conversation.id,
        direction=MessageDirection.OUTBOUND,
        message_type=MessageType.TEMPLATE,
        body_text=None,
        actual_actor_id=actor.employee_id,
        status=MessageStatus.PENDING,
    )

    repository.add_pending_template_message.return_value = pending

    service = OutboundMessageService(
        repository=repository,
        outbox_repository=outbox,
    )

    components = [
        {
            "type": "body",
            "parameters": [
                {
                    "type": "text",
                    "text": "Ahmed",
                }
            ],
        }
    ]

    result = await service.send_template(
        conversation_id=conversation.id,
        template_id=template.id,
        components=components,
        context=context,
        actor=actor,
        idempotency_key="template-123",
    )

    assert result.message.status is MessageStatus.PENDING
    assert not result.idempotent_replay

    repository.last_customer_message_at.assert_not_awaited()

    repository.add_pending_template_message.assert_called_once_with(
        conversation_id=conversation.id,
        template_id=template.id,
        components=components,
        actual_actor_id=(actor.employee_id),
    )

    repository.bind_idempotency_message.assert_awaited_once()

    outbox.add_event.assert_called_once()

    call = outbox.add_event.call_args

    assert call.kwargs["event_type"] == "meta.outbound.send"


@pytest.mark.asyncio
async def test_non_approved_template_is_rejected() -> None:
    (
        conversation,
        group,
        _,
        template,
        context,
        actor,
    ) = _objects()

    template.status = TemplateStatus.PAUSED

    repository = AsyncMock(spec=OutboundMessageRepository)
    outbox = MagicMock(spec=OutboxEventRepository)

    repository.get_conversation.return_value = conversation
    repository.get_active_group.return_value = group
    repository.get_meta_template.return_value = template

    service = OutboundMessageService(
        repository=repository,
        outbox_repository=outbox,
    )

    with pytest.raises(OutboundTemplateNotApprovedError):
        await service.send_template(
            conversation_id=(conversation.id),
            template_id=template.id,
            components=[],
            context=context,
            actor=actor,
            idempotency_key=None,
        )

    repository.add_pending_template_message.assert_not_called()
    outbox.add_event.assert_not_called()


@pytest.mark.asyncio
async def test_template_account_must_match_conversation_number() -> None:
    (
        conversation,
        group,
        number,
        template,
        context,
        actor,
    ) = _objects()

    template.meta_account_id = uuid4()

    repository = AsyncMock(spec=OutboundMessageRepository)
    outbox = MagicMock(spec=OutboxEventRepository)

    repository.get_conversation.return_value = conversation
    repository.get_active_group.return_value = group
    repository.get_meta_template.return_value = template
    repository.get_active_whatsapp_number.return_value = number

    service = OutboundMessageService(
        repository=repository,
        outbox_repository=outbox,
    )

    with pytest.raises(OutboundTemplateAccountMismatchError):
        await service.send_template(
            conversation_id=(conversation.id),
            template_id=template.id,
            components=[],
            context=context,
            actor=actor,
            idempotency_key=None,
        )

    repository.add_pending_template_message.assert_not_called()
