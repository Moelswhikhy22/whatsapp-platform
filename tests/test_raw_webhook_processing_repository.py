from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.raw_webhook_event import (
    RawWebhookEvent,
    RawWebhookProcessingStatus,
    RawWebhookProvider,
)
from app.repositories.raw_webhook_processing import (
    RawWebhookProcessingRepository,
)


NOW = datetime(
    2026,
    10,
    12,
    16,
    0,
    tzinfo=UTC,
)


def _event() -> RawWebhookEvent:
    return RawWebhookEvent(
        id=uuid4(),
        tenant_id=uuid4(),
        provider=RawWebhookProvider.META,
        provider_event_key="test-event",
        event_type="messages",
        payload_json={},
        processing_status=(RawWebhookProcessingStatus.RECEIVED),
        attempts=0,
    )


@pytest.mark.asyncio
async def test_raw_event_lock_uses_for_update() -> None:
    event = _event()

    scalars = MagicMock()
    scalars.first.return_value = event

    session = MagicMock(spec=AsyncSession)
    session.scalars = AsyncMock(return_value=scalars)

    repository = RawWebhookProcessingRepository(session)

    result = await repository.lock_meta_event(event.id)

    assert result is event

    statement = session.scalars.await_args.args[0]

    sql = str(statement.compile(dialect=postgresql.dialect()))

    assert "FOR UPDATE" in sql


def test_mark_processing_increments_attempt() -> None:
    event = _event()

    repository = RawWebhookProcessingRepository(MagicMock(spec=AsyncSession))

    repository.mark_processing(event)

    assert event.processing_status is RawWebhookProcessingStatus.PROCESSING

    assert event.attempts == 1


def test_mark_processed_sets_retention() -> None:
    event = _event()

    repository = RawWebhookProcessingRepository(MagicMock(spec=AsyncSession))

    repository.mark_processed(
        event,
        now=NOW,
    )

    assert event.processing_status is RawWebhookProcessingStatus.PROCESSED

    assert event.processed_at == NOW

    assert event.retention_until is not None

    assert (event.retention_until - NOW).days == 90
