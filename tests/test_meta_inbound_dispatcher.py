from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.db.models.raw_webhook_event import (
    RawWebhookEvent,
    RawWebhookProcessingStatus,
    RawWebhookProvider,
)
from app.repositories.raw_webhook_processing import (
    RawWebhookProcessingRepository,
)
from app.services.incoming_message import (
    IncomingMessageProcessor,
    IncomingMessageUnresolvedError,
)
from app.services.meta_inbound_dispatcher import (
    MetaInboundDispatchOutcome,
    MetaInboundDispatchService,
    MetaInboundPipelineIncompleteError,
    MetaStatusProcessor,
)


def _event(
    *,
    with_messages: bool = True,
    with_statuses: bool = False,
) -> RawWebhookEvent:
    value: dict[str, object] = {}

    if with_messages:
        value["messages"] = [
            {
                "id": "wamid.1",
            }
        ]

    if with_statuses:
        value["statuses"] = [
            {
                "id": "wamid.1",
                "status": "delivered",
            }
        ]

    return RawWebhookEvent(
        id=uuid4(),
        tenant_id=uuid4(),
        provider=RawWebhookProvider.META,
        provider_event_key=(f"test:{uuid4()}"),
        event_type="messages",
        payload_json={
            "entry": [
                {
                    "changes": [
                        {
                            "value": value,
                        }
                    ]
                }
            ]
        },
        processing_status=(RawWebhookProcessingStatus.RECEIVED),
        attempts=0,
    )


@pytest.mark.asyncio
async def test_message_event_is_processed() -> None:
    raw_event = _event()

    repository = AsyncMock(spec=RawWebhookProcessingRepository)

    repository.lock_meta_event.return_value = raw_event

    message_processor = AsyncMock(spec=IncomingMessageProcessor)

    service = MetaInboundDispatchService(
        repository=repository,
        message_processor=message_processor,
    )

    result = await service.dispatch(raw_event_id=raw_event.id)

    message_processor.process_raw_event.assert_awaited_once_with(raw_event)

    repository.mark_processing.assert_called_once_with(raw_event)

    repository.mark_processed.assert_called_once_with(raw_event)

    assert result.outcome is MetaInboundDispatchOutcome.PROCESSED


@pytest.mark.asyncio
async def test_processed_event_is_idempotent_noop() -> None:
    raw_event = _event()

    raw_event.processing_status = RawWebhookProcessingStatus.PROCESSED

    repository = AsyncMock(spec=RawWebhookProcessingRepository)

    repository.lock_meta_event.return_value = raw_event

    processor = AsyncMock(spec=IncomingMessageProcessor)

    service = MetaInboundDispatchService(
        repository=repository,
        message_processor=processor,
    )

    result = await service.dispatch(raw_event_id=raw_event.id)

    processor.process_raw_event.assert_not_awaited()

    repository.mark_processing.assert_not_called()
    repository.mark_processed.assert_not_called()

    assert result.outcome is (MetaInboundDispatchOutcome.ALREADY_PROCESSED)


@pytest.mark.asyncio
async def test_unresolved_message_marks_raw_event_unresolved() -> None:
    raw_event = _event()

    repository = AsyncMock(spec=RawWebhookProcessingRepository)

    repository.lock_meta_event.return_value = raw_event

    processor = AsyncMock(spec=IncomingMessageProcessor)

    processor.process_raw_event.side_effect = IncomingMessageUnresolvedError(
        "CUSTOMER_COMPANY_RESOLUTION_REQUIRED"
    )

    service = MetaInboundDispatchService(
        repository=repository,
        message_processor=processor,
    )

    result = await service.dispatch(raw_event_id=raw_event.id)

    repository.mark_unresolved.assert_called_once_with(
        raw_event,
        error=("CUSTOMER_COMPANY_RESOLUTION_REQUIRED"),
    )

    repository.mark_processed.assert_not_called()

    assert result.outcome is MetaInboundDispatchOutcome.UNRESOLVED


@pytest.mark.asyncio
async def test_status_payload_is_not_silently_discarded() -> None:
    raw_event = _event(
        with_messages=False,
        with_statuses=True,
    )

    repository = AsyncMock(spec=RawWebhookProcessingRepository)

    repository.lock_meta_event.return_value = raw_event

    message_processor = AsyncMock(spec=IncomingMessageProcessor)

    service = MetaInboundDispatchService(
        repository=repository,
        message_processor=message_processor,
        status_processor=None,
    )

    with pytest.raises(MetaInboundPipelineIncompleteError):
        await service.dispatch(raw_event_id=raw_event.id)

    repository.mark_processed.assert_not_called()


@pytest.mark.asyncio
async def test_mixed_event_waits_for_both_processors() -> None:
    raw_event = _event(
        with_messages=True,
        with_statuses=True,
    )

    repository = AsyncMock(spec=RawWebhookProcessingRepository)

    repository.lock_meta_event.return_value = raw_event

    message_processor = AsyncMock(spec=IncomingMessageProcessor)

    status_processor = AsyncMock(spec=MetaStatusProcessor)

    service = MetaInboundDispatchService(
        repository=repository,
        message_processor=message_processor,
        status_processor=status_processor,
    )

    await service.dispatch(raw_event_id=raw_event.id)

    message_processor.process_raw_event.assert_awaited_once_with(raw_event)

    status_processor.process_raw_event.assert_awaited_once_with(raw_event)

    repository.mark_processed.assert_called_once_with(raw_event)

    @pytest.mark.asyncio
    async def test_external_message_echo_is_processed() -> None:
        raw_event = _event(
            with_messages=False,
            with_statuses=False,
        )

        raw_event.payload_json = {
            "entry": [
                {
                    "changes": [
                        {
                            "field": "smb_message_echoes",
                            "value": {
                                "metadata": {
                                    "phone_number_id": ("123456789"),
                                },
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
        }

        repository = AsyncMock(spec=RawWebhookProcessingRepository)

        repository.lock_meta_event.return_value = raw_event

        message_processor = AsyncMock(spec=IncomingMessageProcessor)

        service = MetaInboundDispatchService(
            repository=repository,
            message_processor=message_processor,
        )

        result = await service.dispatch(raw_event_id=raw_event.id)

        message_processor.process_raw_event.assert_awaited_once_with(raw_event)

        repository.mark_processed.assert_called_once_with(raw_event)

        assert result.outcome is (MetaInboundDispatchOutcome.PROCESSED)
