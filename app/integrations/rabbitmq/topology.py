from __future__ import annotations

from aio_pika import ExchangeType
from aio_pika.abc import (
    AbstractExchange,
    AbstractRobustChannel,
)

EXCHANGE_NAME = "whatsapp.platform"
RETRY_EXCHANGE_NAME = "whatsapp.platform.retry"
DEAD_LETTER_EXCHANGE_NAME = "whatsapp.platform.dlx"

RETRY_DELAY_MILLISECONDS = 5_000

META_INBOUND_QUEUE = "meta.inbound"
META_OUTBOUND_QUEUE = "meta.outbound"
MEDIA_PROCESS_QUEUE = "media.process"
ODOO_SYNC_QUEUE = "odoo.sync"
WEBHOOK_DELIVERY_QUEUE = "webhook.delivery"

QUEUE_NAMES: tuple[str, ...] = (
    META_INBOUND_QUEUE,
    META_OUTBOUND_QUEUE,
    MEDIA_PROCESS_QUEUE,
    ODOO_SYNC_QUEUE,
    WEBHOOK_DELIVERY_QUEUE,
)


class UnsupportedOutboxEventTypeError(ValueError):
    """Raised when an outbox event has no broker route."""


def retry_queue_name(
    queue_name: str,
) -> str:
    return f"{queue_name}.retry"


def dead_letter_queue_name(
    queue_name: str,
) -> str:
    return f"{queue_name}.dead"


async def declare_topology(
    channel: AbstractRobustChannel,
) -> AbstractExchange:
    exchange = await channel.declare_exchange(
        EXCHANGE_NAME,
        ExchangeType.DIRECT,
        durable=True,
    )

    retry_exchange = await channel.declare_exchange(
        RETRY_EXCHANGE_NAME,
        ExchangeType.DIRECT,
        durable=True,
    )

    dead_letter_exchange = await channel.declare_exchange(
        DEAD_LETTER_EXCHANGE_NAME,
        ExchangeType.DIRECT,
        durable=True,
    )

    for queue_name in QUEUE_NAMES:
        queue = await channel.declare_queue(
            queue_name,
            durable=True,
        )

        await queue.bind(
            exchange,
            routing_key=queue_name,
        )

        # Domain events such as message.* and conversation.*
        # already use the odoo.sync routing key.
        #
        # Bind webhook.delivery to that same routing key so
        # RabbitMQ creates an independent copy for outgoing
        # webhook processing without creating duplicate
        # transactional outbox rows.
        if queue_name == WEBHOOK_DELIVERY_QUEUE:
            await queue.bind(
                exchange,
                routing_key=ODOO_SYNC_QUEUE,
            )

        retry_name = retry_queue_name(
            queue_name,
        )

        retry_queue = await channel.declare_queue(
            retry_name,
            durable=True,
            arguments={
                "x-message-ttl": RETRY_DELAY_MILLISECONDS,
                "x-dead-letter-exchange": EXCHANGE_NAME,
                "x-dead-letter-routing-key": queue_name,
            },
        )

        await retry_queue.bind(
            retry_exchange,
            routing_key=retry_name,
        )

        dead_name = dead_letter_queue_name(
            queue_name,
        )

        dead_queue = await channel.declare_queue(
            dead_name,
            durable=True,
        )

        await dead_queue.bind(
            dead_letter_exchange,
            routing_key=dead_name,
        )

    return exchange


def routing_key_for_event_type(
    event_type: str,
) -> str:
    normalized = event_type.strip().lower()

    if normalized.startswith("meta.inbound"):
        return META_INBOUND_QUEUE

    if normalized.startswith("meta.outbound"):
        return META_OUTBOUND_QUEUE

    if normalized.startswith("media."):
        return MEDIA_PROCESS_QUEUE

    if normalized.startswith(
        (
            "webhook.",
            "outgoing_webhook.",
        )
    ):
        return WEBHOOK_DELIVERY_QUEUE

    if normalized.startswith(
        (
            "odoo.",
            "conversation.",
            "message.",
            "presence.",
            "template.",
        )
    ):
        return ODOO_SYNC_QUEUE

    raise UnsupportedOutboxEventTypeError(f"Unsupported outbox event type: {event_type!r}")
