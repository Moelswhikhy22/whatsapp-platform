from __future__ import annotations

from datetime import (
    UTC,
    datetime,
    timedelta,
)

from sqlalchemy import (
    Select,
    func,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.outbox_event import (
    OutboxEvent,
    OutboxEventStatus,
)


class OutboxPublisherRepository:
    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self._session = session

    async def get_next_ready(
        self,
    ) -> OutboxEvent | None:
        statement: Select[OutboxEvent] = (
            select(OutboxEvent)
            .where(
                OutboxEvent.status == OutboxEventStatus.PENDING,
                OutboxEvent.available_at <= func.now(),
            )
            .order_by(
                OutboxEvent.created_at.asc(),
                OutboxEvent.id.asc(),
            )
            .with_for_update(
                skip_locked=True,
            )
            .limit(1)
        )

        result = await self._session.scalars(
            statement,
        )

        return result.first()

    def mark_published(
        self,
        event: OutboxEvent,
        *,
        now: datetime | None = None,
    ) -> None:
        published_at = now or datetime.now(UTC)

        event.status = OutboxEventStatus.PUBLISHED
        event.attempts += 1
        event.published_at = published_at
        event.last_error = None

    def schedule_retry(
        self,
        event: OutboxEvent,
        *,
        error: str,
        retry_delay_seconds: int,
        now: datetime | None = None,
    ) -> None:
        if retry_delay_seconds < 0:
            raise ValueError(("retry_delay_seconds cannot be negative"))

        failed_at = now or datetime.now(UTC)

        event.status = OutboxEventStatus.PENDING
        event.attempts += 1
        event.last_error = error[:4000]
        event.published_at = None

        event.available_at = failed_at + timedelta(
            seconds=retry_delay_seconds,
        )

    def mark_failed(
        self,
        event: OutboxEvent,
        *,
        error: str,
    ) -> None:
        event.status = OutboxEventStatus.FAILED
        event.attempts += 1
        event.last_error = error[:4000]
        event.published_at = None
