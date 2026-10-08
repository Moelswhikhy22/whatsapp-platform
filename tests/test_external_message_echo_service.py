from unittest.mock import (
    AsyncMock,
    MagicMock,
)
from uuid import uuid4
from datetime import UTC, datetime
import pytest

from app.db.models.message import (
    MessageType,
)
from app.db.models.raw_webhook_event import (
    RawWebhookEvent,
    RawWebhookProcessingStatus,
    RawWebhookProvider,
)
from app.repositories.incoming_message import (
    IncomingMessageRepository,
)
from app.services.incoming_message import (
    IncomingMessageOutcome,
    IncomingMessageProcessor,
)


@pytest.mark.asyncio
async def test_external_echo_does_not_infer_owner() -> None:
    tenant_id = uuid4()
    whatsapp_number_id = uuid4()
    contact_id = uuid4()
    conversation_id = uuid4()
    owner_id = uuid4()
    group_id = uuid4()
    message_id = uuid4()

    repository = MagicMock(spec=IncomingMessageRepository)

    repository.tenant_id = tenant_id

    whatsapp_number = MagicMock()
    whatsapp_number.id = whatsapp_number_id

    contact = MagicMock()
    contact.id = contact_id

    conversation = MagicMock()
    conversation.id = conversation_id
    conversation.group_id = group_id
    conversation.responsible_employee_id = owner_id

    repository.get_active_whatsapp_number = AsyncMock(return_value=whatsapp_number)

    repository.get_contact_by_normalized_phone = AsyncMock(return_value=contact)

    repository.get_conversation = AsyncMock(return_value=conversation)

    repository.insert_external_message_if_new = AsyncMock(return_value=message_id)

    customer_company_resolver = MagicMock()
    owner_unavailability_handler = MagicMock()

    owner_unavailability_handler.handle_new_customer_work = AsyncMock()

    processor = IncomingMessageProcessor(
        repository=repository,
        customer_company_resolver=(customer_company_resolver),
        owner_unavailability_handler=(owner_unavailability_handler),
    )

    raw_event = RawWebhookEvent(
        id=uuid4(),
        tenant_id=tenant_id,
        provider=RawWebhookProvider.META,
        provider_event_key=(f"echo:{uuid4()}"),
        event_type="smb_message_echoes",
        payload_json={
            "entry": [
                {
                    "changes": [
                        {
                            "field": ("smb_message_echoes"),
                            "value": {
                                "metadata": {"phone_number_id": ("123456789")},
                                "message_echoes": [
                                    {
                                        "from": ("201000000000"),
                                        "to": ("201111111111"),
                                        "id": ("wamid.echo.1"),
                                        "timestamp": ("1760432400"),
                                        "type": "text",
                                        "text": {"body": ("External reply")},
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

    result = await processor.process_raw_event(raw_event)

    assert result.outcome is (IncomingMessageOutcome.PROCESSED)

    assert result.created_message_count == 1
    assert result.created_conversation_count == 0

    repository.get_contact_by_normalized_phone.assert_awaited_once_with("201111111111")

    repository.get_conversation.assert_awaited_once_with(
        whatsapp_number_id=whatsapp_number_id,
        customer_contact_id=contact_id,
    )

    repository.insert_external_message_if_new.assert_awaited_once_with(
        conversation_id=conversation_id,
        meta_message_id="wamid.echo.1",
        message_type=MessageType.TEXT,
        body_text="External reply",
        meta_timestamp=datetime.fromtimestamp(
            1760432400,
            tz=UTC,
        ),
    )

    repository.get_or_create_conversation.assert_not_awaited()
    repository.reopen_if_closed.assert_not_awaited()
    repository.assign_group_if_missing.assert_not_awaited()

    owner_unavailability_handler.handle_new_customer_work.assert_not_awaited()

    repository.add_outbox_event.assert_called_once_with(
        event_type="message.sent",
        aggregate_type="message",
        aggregate_id=str(message_id),
        payload_json={
            "message_id": str(message_id),
            "conversation_id": str(conversation_id),
            "group_id": str(group_id),
            "customer_contact_id": str(contact_id),
            "source": "whatsapp_external",
        },
    )


def result_timestamp():
    from datetime import UTC, datetime

    return datetime.fromtimestamp(
        1760432400,
        tz=UTC,
    )
