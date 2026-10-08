from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import Select, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.raw_webhook_event import (
    RawWebhookEvent,
    RawWebhookProcessingStatus,
    RawWebhookProvider,
)

SUCCESS_RETENTION_DAYS = 90


class RawWebhookProcessingRepository:
    """
    System-worker repository.

    The initial row lookup cannot be tenant-scoped because the raw event ID
    is the trusted durable job identity. Tenant scope is resolved from the
    locked event before any tenant business repository is constructed.
    """

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self._session = session

    async def lock_meta_event(
        self,
        raw_event_id: UUID,
    ) -> RawWebhookEvent | None:
        statement: Select[RawWebhookEvent] = (
            select(RawWebhookEvent)
            .where(
                RawWebhookEvent.id == raw_event_id,
                RawWebhookEvent.provider == RawWebhookProvider.META,
            )
            .with_for_update()
        )

        result = await self._session.scalars(statement)

        return result.first()

    def mark_processing(
        self,
        event: RawWebhookEvent,
    ) -> None:
        event.processing_status = RawWebhookProcessingStatus.PROCESSING

        event.attempts += 1
        event.last_error = None
        event.processed_at = None
        event.retention_until = None

    def mark_processed(
        self,
        event: RawWebhookEvent,
        *,
        now: datetime | None = None,
    ) -> None:
        processed_at = now or datetime.now(UTC)

        event.processing_status = RawWebhookProcessingStatus.PROCESSED

        event.last_error = None
        event.processed_at = processed_at

        event.retention_until = processed_at + timedelta(
            days=SUCCESS_RETENTION_DAYS,
        )

    def mark_unresolved(
        self,
        event: RawWebhookEvent,
        *,
        error: str,
    ) -> None:
        event.processing_status = RawWebhookProcessingStatus.UNRESOLVED

        event.last_error = error[:4000]
        event.processed_at = None
        event.retention_until = None

    async def record_failed_attempt(
        self,
        *,
        raw_event_id: UUID,
        error: str,
    ) -> bool:
        statement = (
            update(RawWebhookEvent)
            .where(
                RawWebhookEvent.id == raw_event_id,
                RawWebhookEvent.provider == RawWebhookProvider.META,
                RawWebhookEvent.processing_status != RawWebhookProcessingStatus.PROCESSED,
            )
            .values(
                processing_status=(RawWebhookProcessingStatus.FAILED),
                attempts=(RawWebhookEvent.attempts + 1),
                last_error=error[:4000],
                processed_at=None,
                retention_until=None,
            )
            .returning(RawWebhookEvent.id)
        )

        result = await self._session.execute(statement)

        return result.scalar_one_or_none() is not None
