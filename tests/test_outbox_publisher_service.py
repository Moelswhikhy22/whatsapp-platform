from unittest.mock import (
    AsyncMock,
    MagicMock,
)
from uuid import uuid4

import pytest

from app.db.models.outbox_event import OutboxEvent
from app.integrations.rabbitmq.outbox_publisher import (
    RabbitMQOutboxPublisher,
)
from app.repositories.outbox_publisher import (
    OutboxPublisherRepository,
)
from app.services.outbox_publisher import (
    OutboxPublishOutcome,
    OutboxPublisherService,
)


def _event(
    attempts: int = 0,
) -> MagicMock:
    event = MagicMock(
        spec=OutboxEvent,
    )

    event.id = uuid4()
    event.attempts = attempts

    return event


@pytest.mark.asyncio
async def test_idle_when_no_event_is_ready() -> None:
    repository = AsyncMock(
        spec=OutboxPublisherRepository,
    )

    repository.get_next_ready.return_value = None

    broker = AsyncMock(
        spec=RabbitMQOutboxPublisher,
    )

    service = OutboxPublisherService(
        repository=repository,
        broker=broker,
    )

    result = await service.publish_next()

    assert result.outcome is OutboxPublishOutcome.IDLE

    broker.publish.assert_not_awaited()


@pytest.mark.asyncio
async def test_success_marks_event_published() -> None:
    event = _event()

    repository = AsyncMock(
        spec=OutboxPublisherRepository,
    )

    repository.get_next_ready.return_value = event

    broker = AsyncMock(
        spec=RabbitMQOutboxPublisher,
    )

    service = OutboxPublisherService(
        repository=repository,
        broker=broker,
    )

    result = await service.publish_next()

    broker.publish.assert_awaited_once_with(
        event,
    )

    repository.mark_published.assert_called_once_with(
        event,
    )

    assert result.outcome is OutboxPublishOutcome.PUBLISHED


@pytest.mark.asyncio
async def test_failure_uses_exponential_retry() -> None:
    event = _event(
        attempts=2,
    )

    repository = AsyncMock(
        spec=OutboxPublisherRepository,
    )

    repository.get_next_ready.return_value = event

    broker = AsyncMock(
        spec=RabbitMQOutboxPublisher,
    )

    broker.publish.side_effect = ConnectionError("broker unavailable")

    service = OutboxPublisherService(
        repository=repository,
        broker=broker,
        max_attempts=10,
        base_retry_delay_seconds=5,
    )

    result = await service.publish_next()

    repository.schedule_retry.assert_called_once_with(
        event,
        error=("ConnectionError: RabbitMQ publish failed"),
        retry_delay_seconds=20,
    )

    repository.mark_failed.assert_not_called()

    assert result.outcome is OutboxPublishOutcome.RETRY_SCHEDULED


@pytest.mark.asyncio
async def test_final_attempt_marks_event_failed() -> None:
    event = _event(
        attempts=4,
    )

    repository = AsyncMock(
        spec=OutboxPublisherRepository,
    )

    repository.get_next_ready.return_value = event

    broker = AsyncMock(
        spec=RabbitMQOutboxPublisher,
    )

    broker.publish.side_effect = ConnectionError("broker unavailable")

    service = OutboxPublisherService(
        repository=repository,
        broker=broker,
        max_attempts=5,
    )

    result = await service.publish_next()

    repository.mark_failed.assert_called_once_with(
        event,
        error=("ConnectionError: RabbitMQ publish failed"),
    )

    repository.schedule_retry.assert_not_called()

    assert result.outcome is OutboxPublishOutcome.FAILED


def test_retry_delay_is_capped() -> None:
    repository = MagicMock(
        spec=OutboxPublisherRepository,
    )

    broker = MagicMock(
        spec=RabbitMQOutboxPublisher,
    )

    service = OutboxPublisherService(
        repository=repository,
        broker=broker,
        base_retry_delay_seconds=5,
        max_retry_delay_seconds=60,
    )

    assert service._retry_delay(10) == 60
