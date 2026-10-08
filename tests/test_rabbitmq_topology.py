from __future__ import annotations

from unittest.mock import (
    AsyncMock,
    MagicMock,
)

import pytest
from aio_pika import ExchangeType

from app.integrations.rabbitmq.topology import (
    DEAD_LETTER_EXCHANGE_NAME,
    EXCHANGE_NAME,
    MEDIA_PROCESS_QUEUE,
    META_INBOUND_QUEUE,
    META_OUTBOUND_QUEUE,
    ODOO_SYNC_QUEUE,
    QUEUE_NAMES,
    RETRY_DELAY_MILLISECONDS,
    RETRY_EXCHANGE_NAME,
    WEBHOOK_DELIVERY_QUEUE,
    UnsupportedOutboxEventTypeError,
    dead_letter_queue_name,
    declare_topology,
    retry_queue_name,
    routing_key_for_event_type,
)


def test_queue_names_are_stable() -> None:
    assert QUEUE_NAMES == (
        META_INBOUND_QUEUE,
        META_OUTBOUND_QUEUE,
        MEDIA_PROCESS_QUEUE,
        ODOO_SYNC_QUEUE,
        WEBHOOK_DELIVERY_QUEUE,
    )


def test_retry_queue_name() -> None:
    assert retry_queue_name(META_INBOUND_QUEUE) == "meta.inbound.retry"


def test_dead_letter_queue_name() -> None:
    assert dead_letter_queue_name(META_INBOUND_QUEUE) == "meta.inbound.dead"


@pytest.mark.parametrize(
    (
        "event_type",
        "expected_queue",
    ),
    [
        (
            "meta.inbound.received",
            META_INBOUND_QUEUE,
        ),
        (
            "meta.outbound.send",
            META_OUTBOUND_QUEUE,
        ),
        (
            "media.process",
            MEDIA_PROCESS_QUEUE,
        ),
        (
            "webhook.delivery",
            WEBHOOK_DELIVERY_QUEUE,
        ),
        (
            "outgoing_webhook.retry",
            WEBHOOK_DELIVERY_QUEUE,
        ),
        (
            "odoo.sync",
            ODOO_SYNC_QUEUE,
        ),
        (
            "conversation.claimed",
            ODOO_SYNC_QUEUE,
        ),
        (
            "message.received",
            ODOO_SYNC_QUEUE,
        ),
        (
            "presence.changed",
            ODOO_SYNC_QUEUE,
        ),
        (
            "template.updated",
            ODOO_SYNC_QUEUE,
        ),
    ],
)
def test_routing_key_for_supported_event_type(
    event_type: str,
    expected_queue: str,
) -> None:
    assert routing_key_for_event_type(event_type) == expected_queue


def test_routing_key_is_case_insensitive() -> None:
    assert routing_key_for_event_type("MESSAGE.RECEIVED") == ODOO_SYNC_QUEUE


def test_routing_key_strips_whitespace() -> None:
    assert routing_key_for_event_type("  webhook.delivery  ") == WEBHOOK_DELIVERY_QUEUE


def test_unsupported_event_type_is_rejected() -> None:
    with pytest.raises(UnsupportedOutboxEventTypeError):
        routing_key_for_event_type("unknown.event")


@pytest.mark.asyncio
async def test_declares_durable_topology() -> None:
    channel = MagicMock()

    main_exchange = MagicMock()
    retry_exchange = MagicMock()
    dead_exchange = MagicMock()

    channel.declare_exchange = AsyncMock(
        side_effect=[
            main_exchange,
            retry_exchange,
            dead_exchange,
        ],
    )

    queues: dict[str, MagicMock] = {}

    async def declare_queue(
        name: str,
        **_: object,
    ) -> MagicMock:
        queue = MagicMock()
        queue.bind = AsyncMock()
        queues[name] = queue
        return queue

    channel.declare_queue = AsyncMock(
        side_effect=declare_queue,
    )

    result = await declare_topology(
        channel,
    )

    assert result is main_exchange

    assert channel.declare_exchange.await_count == 3

    channel.declare_exchange.assert_any_await(
        EXCHANGE_NAME,
        ExchangeType.DIRECT,
        durable=True,
    )

    channel.declare_exchange.assert_any_await(
        RETRY_EXCHANGE_NAME,
        ExchangeType.DIRECT,
        durable=True,
    )

    channel.declare_exchange.assert_any_await(
        DEAD_LETTER_EXCHANGE_NAME,
        ExchangeType.DIRECT,
        durable=True,
    )

    assert channel.declare_queue.await_count == len(QUEUE_NAMES) * 3

    for queue_name in QUEUE_NAMES:
        retry_name = retry_queue_name(queue_name)

        dead_name = dead_letter_queue_name(queue_name)

        channel.declare_queue.assert_any_await(
            queue_name,
            durable=True,
        )

        channel.declare_queue.assert_any_await(
            retry_name,
            durable=True,
            arguments={
                "x-message-ttl": (RETRY_DELAY_MILLISECONDS),
                "x-dead-letter-exchange": (EXCHANGE_NAME),
                "x-dead-letter-routing-key": (queue_name),
            },
        )

        channel.declare_queue.assert_any_await(
            dead_name,
            durable=True,
        )

        queues[queue_name].bind.assert_any_await(
            main_exchange,
            routing_key=queue_name,
        )

        if queue_name == WEBHOOK_DELIVERY_QUEUE:
            queues[queue_name].bind.assert_any_await(
                main_exchange,
                routing_key=(ODOO_SYNC_QUEUE),
            )

            assert queues[queue_name].bind.await_count == 2

        else:
            assert queues[queue_name].bind.await_count == 1

        queues[retry_name].bind.assert_awaited_once_with(
            retry_exchange,
            routing_key=retry_name,
        )

        queues[dead_name].bind.assert_awaited_once_with(
            dead_exchange,
            routing_key=dead_name,
        )


@pytest.mark.asyncio
async def test_webhook_delivery_queue_receives_domain_events() -> None:
    channel = MagicMock()

    main_exchange = MagicMock()
    retry_exchange = MagicMock()
    dead_exchange = MagicMock()

    channel.declare_exchange = AsyncMock(
        side_effect=[
            main_exchange,
            retry_exchange,
            dead_exchange,
        ],
    )

    queues: dict[str, MagicMock] = {}

    async def declare_queue(
        name: str,
        **_: object,
    ) -> MagicMock:
        queue = MagicMock()
        queue.bind = AsyncMock()
        queues[name] = queue
        return queue

    channel.declare_queue = AsyncMock(
        side_effect=declare_queue,
    )

    await declare_topology(
        channel,
    )

    webhook_queue = queues[WEBHOOK_DELIVERY_QUEUE]

    webhook_queue.bind.assert_any_await(
        main_exchange,
        routing_key=(WEBHOOK_DELIVERY_QUEUE),
    )

    webhook_queue.bind.assert_any_await(
        main_exchange,
        routing_key=ODOO_SYNC_QUEUE,
    )

    assert webhook_queue.bind.await_count == 2
