from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from aio_pika import DeliveryMode

from app.db.models.outbox_event import OutboxEvent
from app.integrations.rabbitmq.outbox_publisher import (
    RabbitMQOutboxPublisher,
)
from app.integrations.rabbitmq.topology import (
    ODOO_SYNC_QUEUE,
)


@pytest.mark.asyncio
async def test_publishes_persistent_outbox_message() -> None:
    tenant_id = uuid4()
    event_id = uuid4()

    event = OutboxEvent(
        id=event_id,
        tenant_id=tenant_id,
        event_type="conversation.queued",
        aggregate_type="conversation",
        aggregate_id="conversation-123",
        payload_json={
            "conversation_id": "conversation-123",
        },
        created_at=datetime(
            2026,
            10,
            12,
            12,
            0,
            tzinfo=UTC,
        ),
    )

    exchange = MagicMock()
    exchange.publish = AsyncMock(
        return_value=True,
    )

    publisher = RabbitMQOutboxPublisher(
        exchange,
    )

    await publisher.publish(event)

    exchange.publish.assert_awaited_once()

    message = exchange.publish.await_args.args[0]

    assert exchange.publish.await_args.kwargs["routing_key"] == ODOO_SYNC_QUEUE

    assert exchange.publish.await_args.kwargs["mandatory"] is True

    assert message.delivery_mode is DeliveryMode.PERSISTENT

    assert message.message_id == str(event_id)
    assert message.type == "conversation.queued"

    payload = json.loads(message.body.decode("utf-8"))

    assert payload["event_id"] == str(
        event_id,
    )
    assert payload["tenant_id"] == str(
        tenant_id,
    )
    assert payload["aggregate_id"] == "conversation-123"
