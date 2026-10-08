from __future__ import annotations

from unittest.mock import (
    AsyncMock,
    MagicMock,
)
from uuid import uuid4

import pytest

from app.db.models.message import (
    Message,
    MessageDirection,
    MessageStatus,
    MessageType,
)
from app.db.models.raw_webhook_event import (
    RawWebhookEvent,
    RawWebhookProcessingStatus,
    RawWebhookProvider,
)
from app.repositories.message_status import (
    MessageStatusRepository,
)
from app.services.message_status import (
    MessageStatusMessageNotFoundError,
    MessageStatusOutcome,
    MessageStatusProcessor,
)


def _raw_event(
    *,
    tenant_id,
    status: str,
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
                            "value": {
                                "statuses": [
                                    {
                                        "id": ("wamid.1"),
                                        "status": status,
                                        "timestamp": ("1791800000"),
                                    }
                                ]
                            }
                        }
                    ]
                }
            ]
        },
        processing_status=(RawWebhookProcessingStatus.PROCESSING),
        attempts=1,
    )


def _message(
    *,
    tenant_id,
    status,
) -> Message:
    return Message(
        id=uuid4(),
        tenant_id=tenant_id,
        conversation_id=uuid4(),
        meta_message_id="wamid.1",
        direction=(MessageDirection.OUTBOUND),
        message_type=MessageType.TEXT,
        body_text="Hello",
        status=status,
    )


@pytest.mark.asyncio
async def test_status_advances_and_publishes_event() -> None:
    tenant_id = uuid4()

    repository = AsyncMock(spec=MessageStatusRepository)

    repository.tenant_id = tenant_id

    message = _message(
        tenant_id=tenant_id,
        status=MessageStatus.SENT,
    )

    repository.get_outbound_message_for_update.return_value = message

    processor = MessageStatusProcessor(repository=repository)

    result = await processor.process_raw_event(
        _raw_event(
            tenant_id=tenant_id,
            status="delivered",
        )
    )

    assert result.outcome is MessageStatusOutcome.PROCESSED

    assert result.history_event_count == 1

    assert result.effective_status_change_count == 1

    repository.add_status_history.assert_called_once()

    repository.set_effective_status.assert_called_once_with(
        message=message,
        status=MessageStatus.DELIVERED,
    )

    repository.add_status_outbox_event.assert_called_once_with(
        message=message,
        status=MessageStatus.DELIVERED,
    )


@pytest.mark.asyncio
async def test_late_sent_does_not_regress_delivered() -> None:
    tenant_id = uuid4()

    repository = AsyncMock(spec=MessageStatusRepository)

    repository.tenant_id = tenant_id

    message = _message(
        tenant_id=tenant_id,
        status=MessageStatus.DELIVERED,
    )

    repository.get_outbound_message_for_update.return_value = message

    processor = MessageStatusProcessor(repository=repository)

    result = await processor.process_raw_event(
        _raw_event(
            tenant_id=tenant_id,
            status="sent",
        )
    )

    assert result.history_event_count == 1

    assert result.effective_status_change_count == 0

    repository.add_status_history.assert_called_once()

    repository.set_effective_status.assert_not_called()

    repository.add_status_outbox_event.assert_not_called()


@pytest.mark.asyncio
async def test_late_failed_does_not_replace_sent() -> None:
    tenant_id = uuid4()

    repository = AsyncMock(spec=MessageStatusRepository)

    repository.tenant_id = tenant_id

    message = _message(
        tenant_id=tenant_id,
        status=MessageStatus.SENT,
    )

    repository.get_outbound_message_for_update.return_value = message

    processor = MessageStatusProcessor(repository=repository)

    result = await processor.process_raw_event(
        _raw_event(
            tenant_id=tenant_id,
            status="failed",
        )
    )

    assert result.history_event_count == 1

    assert result.effective_status_change_count == 0

    repository.set_effective_status.assert_not_called()
    repository.add_status_outbox_event.assert_not_called()


@pytest.mark.asyncio
async def test_failed_can_replace_pending() -> None:
    tenant_id = uuid4()

    repository = AsyncMock(spec=MessageStatusRepository)

    repository.tenant_id = tenant_id

    message = _message(
        tenant_id=tenant_id,
        status=MessageStatus.PENDING,
    )

    repository.get_outbound_message_for_update.return_value = message

    processor = MessageStatusProcessor(repository=repository)

    await processor.process_raw_event(
        _raw_event(
            tenant_id=tenant_id,
            status="failed",
        )
    )

    repository.set_effective_status.assert_called_once_with(
        message=message,
        status=MessageStatus.FAILED,
    )

    repository.add_status_outbox_event.assert_called_once()


@pytest.mark.asyncio
async def test_success_can_advance_previous_failed() -> None:
    tenant_id = uuid4()

    repository = AsyncMock(spec=MessageStatusRepository)

    repository.tenant_id = tenant_id

    message = _message(
        tenant_id=tenant_id,
        status=MessageStatus.FAILED,
    )

    repository.get_outbound_message_for_update.return_value = message

    processor = MessageStatusProcessor(repository=repository)

    await processor.process_raw_event(
        _raw_event(
            tenant_id=tenant_id,
            status="sent",
        )
    )

    repository.set_effective_status.assert_called_once_with(
        message=message,
        status=MessageStatus.SENT,
    )


@pytest.mark.asyncio
async def test_unknown_message_causes_retryable_failure() -> None:
    tenant_id = uuid4()

    repository = AsyncMock(spec=MessageStatusRepository)

    repository.tenant_id = tenant_id

    repository.get_outbound_message_for_update.return_value = None

    processor = MessageStatusProcessor(repository=repository)

    with pytest.raises(MessageStatusMessageNotFoundError):
        await processor.process_raw_event(
            _raw_event(
                tenant_id=tenant_id,
                status="delivered",
            )
        )

    repository.add_status_history.assert_not_called()
    repository.add_status_outbox_event.assert_not_called()
