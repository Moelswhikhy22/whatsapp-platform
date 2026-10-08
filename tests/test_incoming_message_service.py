from __future__ import annotations

from unittest.mock import (
    AsyncMock,
    MagicMock,
)
from uuid import uuid4

import pytest

from app.db.models.conversation import (
    Conversation,
    ConversationState,
)
from app.db.models.customer_contact import (
    CustomerContact,
)
from app.db.models.raw_webhook_event import (
    RawWebhookEvent,
    RawWebhookProcessingStatus,
    RawWebhookProvider,
)
from app.db.models.whatsapp_number import (
    WhatsAppNumber,
)
from app.repositories.incoming_message import (
    IncomingMessageRepository,
)
from app.services.incoming_message import (
    CustomerCompanyResolver,
    IncomingMessageOutcome,
    IncomingMessageProcessor,
    IncomingMessageUnresolvedError,
    OwnerUnavailabilityHandler,
)


def _raw_event(
    *,
    tenant_id,
    message_id: str = "wamid.1",
) -> RawWebhookEvent:
    return RawWebhookEvent(
        id=uuid4(),
        tenant_id=tenant_id,
        provider=RawWebhookProvider.META,
        provider_event_key=(f"test:{uuid4()}"),
        event_type="messages",
        payload_json={
            "entry": [
                {
                    "changes": [
                        {
                            "field": "messages",
                            "value": {
                                "metadata": {
                                    "phone_number_id": ("meta-number-1"),
                                },
                                "contacts": [
                                    {
                                        "wa_id": ("201234567890"),
                                        "profile": {"name": ("Ahmed")},
                                    }
                                ],
                                "messages": [
                                    {
                                        "id": message_id,
                                        "from": ("201234567890"),
                                        "type": "text",
                                        "text": {"body": ("Hello")},
                                    }
                                ],
                            },
                        }
                    ]
                }
            ]
        },
        processing_status=(RawWebhookProcessingStatus.RECEIVED),
        attempts=0,
    )


def _service(
    tenant_id,
):
    repository = AsyncMock(spec=IncomingMessageRepository)

    repository.tenant_id = tenant_id

    company_resolver = AsyncMock(spec=CustomerCompanyResolver)

    owner_handler = AsyncMock(spec=OwnerUnavailabilityHandler)

    service = IncomingMessageProcessor(
        repository=repository,
        customer_company_resolver=(company_resolver),
        owner_unavailability_handler=(owner_handler),
    )

    return (
        service,
        repository,
        company_resolver,
        owner_handler,
    )


def _number(
    tenant_id,
) -> WhatsAppNumber:
    return WhatsAppNumber(
        id=uuid4(),
        tenant_id=tenant_id,
        integration_id=uuid4(),
        meta_phone_number_id=("meta-number-1"),
        display_phone_number=("+201111111111"),
        active=True,
    )


def _contact(
    tenant_id,
) -> CustomerContact:
    return CustomerContact(
        id=uuid4(),
        tenant_id=tenant_id,
        customer_company_id=uuid4(),
        display_name="Ahmed",
        phone_number="+201234567890",
        normalized_phone="201234567890",
        active=True,
    )


def _conversation(
    *,
    tenant_id,
    number_id,
    contact_id,
    group_id,
    state=ConversationState.QUEUED,
    owner_id=None,
) -> Conversation:
    return Conversation(
        id=uuid4(),
        tenant_id=tenant_id,
        whatsapp_number_id=number_id,
        customer_contact_id=contact_id,
        group_id=group_id,
        state=state,
        responsible_employee_id=(owner_id),
    )


@pytest.mark.asyncio
async def test_existing_contact_message_is_persisted() -> None:
    tenant_id = uuid4()
    group_id = uuid4()

    service, repository, _, owner = _service(tenant_id)

    number = _number(tenant_id)
    contact = _contact(tenant_id)

    conversation = _conversation(
        tenant_id=tenant_id,
        number_id=number.id,
        contact_id=contact.id,
        group_id=group_id,
    )

    repository.get_active_whatsapp_number.return_value = number

    repository.get_contact_by_normalized_phone.return_value = contact

    repository.get_conversation.return_value = conversation

    repository.insert_message_if_new.return_value = uuid4()

    result = await service.process_raw_event(_raw_event(tenant_id=tenant_id))

    assert result.outcome is IncomingMessageOutcome.PROCESSED

    assert result.created_message_count == 1
    assert result.created_conversation_count == 0

    repository.insert_message_if_new.assert_awaited_once()

    owner.handle_new_customer_work.assert_not_awaited()

    repository.add_outbox_event.assert_called_once()

    assert repository.add_outbox_event.call_args.kwargs["event_type"] == "message.received"


@pytest.mark.asyncio
async def test_unknown_contact_can_be_created_through_company_resolver() -> None:
    tenant_id = uuid4()
    group_id = uuid4()
    company_id = uuid4()

    (
        service,
        repository,
        resolver,
        _,
    ) = _service(tenant_id)

    number = _number(tenant_id)
    contact = _contact(tenant_id)

    conversation = _conversation(
        tenant_id=tenant_id,
        number_id=number.id,
        contact_id=contact.id,
        group_id=group_id,
    )

    repository.get_active_whatsapp_number.return_value = number

    repository.get_contact_by_normalized_phone.return_value = None

    resolver.resolve_company_id.return_value = company_id

    repository.customer_company_is_active.return_value = True

    repository.get_or_create_contact.return_value = contact

    repository.get_conversation.return_value = None

    repository.list_active_group_ids_for_number.return_value = [group_id]

    repository.get_or_create_conversation.return_value = (
        conversation,
        True,
    )

    repository.list_eligible_team_member_ids.return_value = [
        uuid4(),
        uuid4(),
    ]

    repository.insert_message_if_new.return_value = uuid4()

    result = await service.process_raw_event(_raw_event(tenant_id=tenant_id))

    assert result.created_message_count == 1

    assert result.created_conversation_count == 1

    resolver.resolve_company_id.assert_awaited_once()

    repository.get_or_create_contact.assert_awaited_once()

    assert repository.add_outbox_event.call_count == 2

    event_types = {
        call.kwargs["event_type"] for call in (repository.add_outbox_event.call_args_list)
    }

    assert event_types == {
        "conversation.queued",
        "message.received",
    }


@pytest.mark.asyncio
async def test_unknown_contact_without_company_mapping_is_unresolved() -> None:
    tenant_id = uuid4()

    (
        service,
        repository,
        resolver,
        _,
    ) = _service(tenant_id)

    repository.get_active_whatsapp_number.return_value = _number(tenant_id)

    repository.get_contact_by_normalized_phone.return_value = None

    resolver.resolve_company_id.return_value = None

    with pytest.raises(
        IncomingMessageUnresolvedError,
        match=("CUSTOMER_COMPANY_RESOLUTION_REQUIRED"),
    ):
        await service.process_raw_event(_raw_event(tenant_id=tenant_id))

    repository.get_or_create_contact.assert_not_awaited()

    repository.insert_message_if_new.assert_not_awaited()


@pytest.mark.asyncio
async def test_multiple_groups_are_not_routed_randomly() -> None:
    tenant_id = uuid4()

    service, repository, _, _ = _service(tenant_id)

    number = _number(tenant_id)
    contact = _contact(tenant_id)

    repository.get_active_whatsapp_number.return_value = number

    repository.get_contact_by_normalized_phone.return_value = contact

    repository.get_conversation.return_value = None

    repository.list_active_group_ids_for_number.return_value = [
        uuid4(),
        uuid4(),
    ]

    with pytest.raises(
        IncomingMessageUnresolvedError,
        match=("WHATSAPP_NUMBER_GROUP_ROUTE_AMBIGUOUS"),
    ):
        await service.process_raw_event(_raw_event(tenant_id=tenant_id))

    repository.get_or_create_conversation.assert_not_awaited()


@pytest.mark.asyncio
async def test_closed_conversation_is_reopened() -> None:
    tenant_id = uuid4()
    group_id = uuid4()

    service, repository, _, _ = _service(tenant_id)

    number = _number(tenant_id)
    contact = _contact(tenant_id)

    closed = _conversation(
        tenant_id=tenant_id,
        number_id=number.id,
        contact_id=contact.id,
        group_id=group_id,
        state=ConversationState.CLOSED,
    )

    reopened = _conversation(
        tenant_id=tenant_id,
        number_id=number.id,
        contact_id=contact.id,
        group_id=group_id,
        state=ConversationState.REOPENED,
    )

    reopened.id = closed.id

    repository.get_active_whatsapp_number.return_value = number

    repository.get_contact_by_normalized_phone.return_value = contact

    repository.get_conversation.return_value = closed

    repository.reopen_if_closed.return_value = reopened

    repository.insert_message_if_new.return_value = uuid4()

    await service.process_raw_event(_raw_event(tenant_id=tenant_id))

    repository.reopen_if_closed.assert_awaited_once_with(closed.id)

    event_types = [
        call.kwargs["event_type"] for call in (repository.add_outbox_event.call_args_list)
    ]

    assert event_types == [
        "conversation.reopened",
        "message.received",
    ]


@pytest.mark.asyncio
async def test_duplicate_meta_message_creates_no_second_business_event() -> None:
    tenant_id = uuid4()
    group_id = uuid4()

    service, repository, _, _ = _service(tenant_id)

    number = _number(tenant_id)
    contact = _contact(tenant_id)

    conversation = _conversation(
        tenant_id=tenant_id,
        number_id=number.id,
        contact_id=contact.id,
        group_id=group_id,
    )

    repository.get_active_whatsapp_number.return_value = number

    repository.get_contact_by_normalized_phone.return_value = contact

    repository.get_conversation.return_value = conversation

    repository.insert_message_if_new.return_value = None

    result = await service.process_raw_event(_raw_event(tenant_id=tenant_id))

    assert result.created_message_count == 0

    repository.add_outbox_event.assert_not_called()


@pytest.mark.asyncio
async def test_owned_conversation_triggers_owner_unavailability_policy() -> None:
    tenant_id = uuid4()
    group_id = uuid4()
    owner_id = uuid4()

    (
        service,
        repository,
        _,
        owner,
    ) = _service(tenant_id)

    number = _number(tenant_id)
    contact = _contact(tenant_id)

    conversation = _conversation(
        tenant_id=tenant_id,
        number_id=number.id,
        contact_id=contact.id,
        group_id=group_id,
        owner_id=owner_id,
    )

    repository.get_active_whatsapp_number.return_value = number

    repository.get_contact_by_normalized_phone.return_value = contact

    repository.get_conversation.return_value = conversation

    repository.insert_message_if_new.return_value = uuid4()

    await service.process_raw_event(_raw_event(tenant_id=tenant_id))

    owner.handle_new_customer_work.assert_awaited_once_with(conversation_id=conversation.id)
