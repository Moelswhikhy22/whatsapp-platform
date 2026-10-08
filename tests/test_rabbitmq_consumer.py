from unittest.mock import (
    AsyncMock,
    MagicMock,
)

import pytest

from app.integrations.rabbitmq.consumer import (
    PermanentMessageError,
    ReliableConsumer,
)
from app.integrations.rabbitmq.topology import (
    ODOO_SYNC_QUEUE,
    dead_letter_queue_name,
    retry_queue_name,
)


def _message(
    *,
    retry_count: int = 0,
) -> MagicMock:
    message = MagicMock()

    message.body = b'{"event_id":"1"}'
    message.headers = {
        "x-retry-count": retry_count,
    }

    message.content_type = "application/json"
    message.content_encoding = "utf-8"
    message.message_id = "event-1"
    message.correlation_id = None
    message.type = "message.received"

    message.ack = AsyncMock()
    message.nack = AsyncMock()

    return message


def _consumer(
    handler: AsyncMock,
    *,
    max_attempts: int = 5,
):
    queue = MagicMock()
    queue.consume = AsyncMock()

    retry_exchange = MagicMock()
    retry_exchange.publish = AsyncMock()

    dead_exchange = MagicMock()
    dead_exchange.publish = AsyncMock()

    consumer = ReliableConsumer(
        queue_name=ODOO_SYNC_QUEUE,
        queue=queue,
        retry_exchange=retry_exchange,
        dead_letter_exchange=dead_exchange,
        handler=handler,
        max_attempts=max_attempts,
    )

    return (
        consumer,
        queue,
        retry_exchange,
        dead_exchange,
    )


@pytest.mark.asyncio
async def test_success_acknowledges_message() -> None:
    handler = AsyncMock()

    consumer, _, retry, dead = _consumer(
        handler,
    )

    message = _message()

    await consumer.handle_message(
        message,
    )

    handler.assert_awaited_once_with(
        message,
    )

    message.ack.assert_awaited_once()
    message.nack.assert_not_awaited()

    retry.publish.assert_not_awaited()
    dead.publish.assert_not_awaited()


@pytest.mark.asyncio
async def test_transient_failure_moves_to_retry_queue() -> None:
    handler = AsyncMock(side_effect=RuntimeError("temporary failure"))

    consumer, _, retry, dead = _consumer(
        handler,
    )

    message = _message()

    await consumer.handle_message(
        message,
    )

    retry.publish.assert_awaited_once()

    retry_message = retry.publish.await_args.args[0]

    assert retry.publish.await_args.kwargs["routing_key"] == retry_queue_name(ODOO_SYNC_QUEUE)

    assert retry_message.headers["x-retry-count"] == 1

    message.ack.assert_awaited_once()
    message.nack.assert_not_awaited()

    dead.publish.assert_not_awaited()


@pytest.mark.asyncio
async def test_exhausted_message_moves_to_dead_queue() -> None:
    handler = AsyncMock(side_effect=RuntimeError("still failing"))

    consumer, _, retry, dead = _consumer(
        handler,
        max_attempts=3,
    )

    message = _message(
        retry_count=2,
    )

    await consumer.handle_message(
        message,
    )

    retry.publish.assert_not_awaited()
    dead.publish.assert_awaited_once()

    dead_message = dead.publish.await_args.args[0]

    assert dead.publish.await_args.kwargs["routing_key"] == dead_letter_queue_name(ODOO_SYNC_QUEUE)

    assert dead_message.headers["x-dead-letter-reason"] == "max_attempts_exhausted"

    message.ack.assert_awaited_once()


@pytest.mark.asyncio
async def test_permanent_failure_moves_directly_to_dead_queue() -> None:
    handler = AsyncMock(side_effect=PermanentMessageError("invalid payload"))

    consumer, _, retry, dead = _consumer(
        handler,
    )

    message = _message()

    await consumer.handle_message(
        message,
    )

    retry.publish.assert_not_awaited()
    dead.publish.assert_awaited_once()

    dead_message = dead.publish.await_args.args[0]

    assert dead_message.headers["x-dead-letter-reason"] == "permanent_failure"

    message.ack.assert_awaited_once()


@pytest.mark.asyncio
async def test_retry_publish_failure_requeues_original() -> None:
    handler = AsyncMock(side_effect=RuntimeError("temporary failure"))

    consumer, _, retry, _ = _consumer(
        handler,
    )

    retry.publish.side_effect = ConnectionError("broker publish failed")

    message = _message()

    await consumer.handle_message(
        message,
    )

    message.ack.assert_not_awaited()

    message.nack.assert_awaited_once_with(
        requeue=True,
    )


@pytest.mark.asyncio
async def test_consumer_uses_manual_acknowledgements() -> None:
    handler = AsyncMock()

    consumer, queue, _, _ = _consumer(
        handler,
    )

    await consumer.start()

    queue.consume.assert_awaited_once_with(
        consumer.handle_message,
        no_ack=False,
    )
