from __future__ import annotations

import json

from aio_pika import DeliveryMode, Message
from aio_pika.abc import AbstractExchange

from app.db.models.outbox_event import OutboxEvent
from app.integrations.rabbitmq.topology import (
    routing_key_for_event_type,
)


class RabbitMQOutboxPublisher:
    def __init__(
        self,
        exchange: AbstractExchange,
    ) -> None:
        self._exchange = exchange

    async def publish(
        self,
        event: OutboxEvent,
    ) -> None:
        event_id = str(event.id)

        envelope: dict[str, object] = {
            "event_id": event_id,
            "tenant_id": str(event.tenant_id),
            "event_type": event.event_type,
            "aggregate_type": event.aggregate_type,
            "aggregate_id": event.aggregate_id,
            "occurred_at": event.created_at.isoformat(),
            "payload": event.payload_json,
        }

        body = json.dumps(
            envelope,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")

        message = Message(
            body=body,
            content_type="application/json",
            content_encoding="utf-8",
            delivery_mode=DeliveryMode.PERSISTENT,
            message_id=event_id,
            type=event.event_type,
            headers={
                "event_id": event_id,
                "tenant_id": str(event.tenant_id),
                "aggregate_type": event.aggregate_type,
                "aggregate_id": event.aggregate_id,
            },
        )

        await self._exchange.publish(
            message,
            routing_key=routing_key_for_event_type(
                event.event_type,
            ),
            mandatory=True,
        )
