from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from app.db.models.outbox_event import (
    OutboxEvent,
)
from app.integrations.rabbitmq.outbox_publisher import (
    RabbitMQOutboxPublisher,
)
from app.repositories.outbox_publisher import (
    OutboxPublisherRepository,
)


class OutboxPublishOutcome(StrEnum):
    IDLE = "idle"
    PUBLISHED = "published"
    RETRY_SCHEDULED = "retry_scheduled"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class OutboxPublishResult:
    outcome: OutboxPublishOutcome
    event_id: UUID | None = None


class OutboxPublisherService:
    def __init__(
        self,
        *,
        repository: OutboxPublisherRepository,
        broker: RabbitMQOutboxPublisher,
        max_attempts: int = 10,
        base_retry_delay_seconds: int = 5,
        max_retry_delay_seconds: int = 300,
    ) -> None:
        if max_attempts <= 0:
            raise ValueError("max_attempts must be greater than zero")

        if base_retry_delay_seconds <= 0:
            raise ValueError(("base_retry_delay_seconds must be greater than zero"))

        if max_retry_delay_seconds < base_retry_delay_seconds:
            raise ValueError(("max_retry_delay_seconds must be >= base_retry_delay_seconds"))

        self._repository = repository
        self._broker = broker
        self._max_attempts = max_attempts

        self._base_retry_delay_seconds = base_retry_delay_seconds

        self._max_retry_delay_seconds = max_retry_delay_seconds

    async def publish_next(
        self,
    ) -> OutboxPublishResult:
        event = await self._repository.get_next_ready()

        if event is None:
            return OutboxPublishResult(
                outcome=OutboxPublishOutcome.IDLE,
            )

        try:
            await self._broker.publish(
                event,
            )
        except Exception as exc:
            return self._handle_failure(
                event,
                exc,
            )

        self._repository.mark_published(
            event,
        )

        return OutboxPublishResult(
            outcome=(OutboxPublishOutcome.PUBLISHED),
            event_id=event.id,
        )

    def _handle_failure(
        self,
        event: OutboxEvent,
        exc: Exception,
    ) -> OutboxPublishResult:
        safe_error = f"{type(exc).__name__}: RabbitMQ publish failed"

        next_attempt = event.attempts + 1

        if next_attempt >= self._max_attempts:
            self._repository.mark_failed(
                event,
                error=safe_error,
            )

            return OutboxPublishResult(
                outcome=(OutboxPublishOutcome.FAILED),
                event_id=event.id,
            )

        delay = self._retry_delay(
            event.attempts,
        )

        self._repository.schedule_retry(
            event,
            error=safe_error,
            retry_delay_seconds=delay,
        )

        return OutboxPublishResult(
            outcome=(OutboxPublishOutcome.RETRY_SCHEDULED),
            event_id=event.id,
        )

    def _retry_delay(
        self,
        previous_attempts: int,
    ) -> int:
        if previous_attempts < 0:
            raise ValueError("previous_attempts cannot be negative")

        multiplier: int = 1 << previous_attempts

        delay: int = self._base_retry_delay_seconds * multiplier

        if delay > self._max_retry_delay_seconds:
            return self._max_retry_delay_seconds

        return delay
