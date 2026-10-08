from __future__ import annotations

import os
from uuid import uuid4

import pytest
from aio_pika import (
    DeliveryMode,
    Message,
)

from app.integrations.rabbitmq.client import (
    RabbitMQClient,
)
from app.integrations.rabbitmq.metrics import (
    collect_queue_metrics,
)
from app.integrations.rabbitmq.topology import (
    EXCHANGE_NAME,
    QUEUE_NAMES,
    declare_topology,
)


pytestmark = pytest.mark.integration


def _rabbitmq_test_url() -> str:
    value = os.getenv("RABBITMQ_TEST_URL")

    if not value:
        pytest.skip("RABBITMQ_TEST_URL is not configured.")

    return value


@pytest.mark.asyncio
async def test_real_rabbitmq_topology_and_publish() -> None:
    client = RabbitMQClient(_rabbitmq_test_url())

    await client.connect()

    channel = await client.open_channel()

    try:
        exchange = await declare_topology(
            channel,
        )

        routing_key = f"integration.test.{uuid4()}"

        queue = await channel.declare_queue(
            "",
            exclusive=True,
            auto_delete=True,
            robust=False,
        )

        await queue.bind(
            exchange,
            routing_key=routing_key,
        )

        body = b"rabbitmq-integration-test"

        await exchange.publish(
            Message(
                body=body,
                delivery_mode=(DeliveryMode.PERSISTENT),
                message_id=str(uuid4()),
            ),
            routing_key=routing_key,
            mandatory=True,
        )

        message = await queue.get(
            fail=False,
            timeout=5,
        )

        assert message is not None
        assert message.body == body

        await message.ack()

        metrics = await collect_queue_metrics(
            channel,
        )

        metric_names = {metric.queue_name for metric in metrics}

        for queue_name in QUEUE_NAMES:
            assert queue_name in metric_names

    finally:
        if not channel.is_closed:
            await channel.close()

        await client.close()


@pytest.mark.asyncio
async def test_topology_is_idempotent_after_reconnect() -> None:
    url = _rabbitmq_test_url()

    first_client = RabbitMQClient(url)

    await first_client.connect()

    first_channel = await first_client.open_channel()

    try:
        first_exchange = await declare_topology(
            first_channel,
        )

        assert first_exchange.name == EXCHANGE_NAME
    finally:
        if not first_channel.is_closed:
            await first_channel.close()

        await first_client.close()

    second_client = RabbitMQClient(url)

    await second_client.connect()

    second_channel = await second_client.open_channel()

    try:
        second_exchange = await declare_topology(
            second_channel,
        )

        assert second_exchange.name == EXCHANGE_NAME

        for queue_name in QUEUE_NAMES:
            queue = await second_channel.declare_queue(
                queue_name,
                passive=True,
                robust=False,
            )

            assert queue.name == queue_name
    finally:
        if not second_channel.is_closed:
            await second_channel.close()

        await second_client.close()
