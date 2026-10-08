from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.integrations.rabbitmq.metrics import (
    collect_queue_metrics,
    monitored_queue_names,
)
from app.integrations.rabbitmq.topology import (
    QUEUE_NAMES,
    dead_letter_queue_name,
    retry_queue_name,
)


def test_monitored_queue_names_include_main_retry_and_dead() -> None:
    result = monitored_queue_names()

    assert len(result) == len(QUEUE_NAMES) * 3

    for queue_name in QUEUE_NAMES:
        assert queue_name in result
        assert retry_queue_name(queue_name) in result
        assert dead_letter_queue_name(queue_name) in result


@pytest.mark.asyncio
async def test_collect_queue_metrics() -> None:
    channel = MagicMock()

    queues = []

    for index, _ in enumerate(
        monitored_queue_names(),
    ):
        queue = MagicMock()

        queue.declare = AsyncMock(
            return_value=SimpleNamespace(
                message_count=index + 1,
                consumer_count=index,
            )
        )

        queues.append(queue)

    channel.declare_queue = AsyncMock(
        side_effect=queues,
    )

    result = await collect_queue_metrics(
        channel,
    )

    assert len(result) == len(monitored_queue_names())

    assert result[0].message_count == 1
    assert result[0].consumer_count == 0

    assert channel.declare_queue.await_count == len(monitored_queue_names())

    for queue_name in monitored_queue_names():
        channel.declare_queue.assert_any_await(
            queue_name,
            passive=True,
            robust=False,
        )
