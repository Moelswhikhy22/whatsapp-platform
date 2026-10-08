from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import (
    AsyncMock,
    MagicMock,
)
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.outbox_event import (
    OutboxEvent,
    OutboxEventStatus,
)
from app.repositories.outbox_publisher import (
    OutboxPublisherRepository,
)


NOW = datetime(
    2026,
    10,
    12,
    12,
    0,
    tzinfo=UTC,
)


def _event() -> OutboxEvent:
    return OutboxEvent(
        id=uuid4(),
        tenant_id=uuid4(),
        event_type="conversation.queued",
        aggregate_type="conversation",
        aggregate_id="conversation-1",
        payload_json={},
        status=OutboxEventStatus.PENDING,
        attempts=0,
        available_at=NOW,
        created_at=NOW,
    )


@pytest.mark.asyncio
async def test_polling_query_uses_skip_locked() -> None:
    event = _event()

    scalars_result = MagicMock()
    scalars_result.first.return_value = event

    session = MagicMock(
        spec=AsyncSession,
    )

    session.scalars = AsyncMock(
        return_value=scalars_result,
    )

    repository = OutboxPublisherRepository(
        session,
    )

    result = await repository.get_next_ready()

    assert result is event

    statement = session.scalars.await_args.args[0]

    sql = str(
        statement.compile(
            dialect=postgresql.dialect(),
        )
    )

    assert "FOR UPDATE SKIP LOCKED" in sql


def test_mark_published_updates_event() -> None:
    event = _event()

    repository = OutboxPublisherRepository(
        MagicMock(
            spec=AsyncSession,
        ),
    )

    repository.mark_published(
        event,
        now=NOW,
    )

    assert event.status is OutboxEventStatus.PUBLISHED

    assert event.attempts == 1
    assert event.published_at == NOW
    assert event.last_error is None


def test_schedule_retry_keeps_pending() -> None:
    event = _event()

    repository = OutboxPublisherRepository(
        MagicMock(
            spec=AsyncSession,
        ),
    )

    repository.schedule_retry(
        event,
        error="ConnectionError",
        retry_delay_seconds=5,
        now=NOW,
    )

    assert event.status is OutboxEventStatus.PENDING

    assert event.attempts == 1
    assert event.published_at is None
    assert event.last_error == "ConnectionError"

    assert event.available_at.timestamp() == NOW.timestamp() + 5


def test_mark_failed_stops_publication() -> None:
    event = _event()
    event.attempts = 4

    repository = OutboxPublisherRepository(
        MagicMock(
            spec=AsyncSession,
        ),
    )

    repository.mark_failed(
        event,
        error="publish failed",
    )

    assert event.status is OutboxEventStatus.FAILED

    assert event.attempts == 5
    assert event.last_error == "publish failed"
    assert event.published_at is None
