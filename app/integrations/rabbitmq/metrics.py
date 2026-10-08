from __future__ import annotations

from dataclasses import dataclass

from aio_pika.abc import AbstractRobustChannel

from app.integrations.rabbitmq.topology import (
    QUEUE_NAMES,
    dead_letter_queue_name,
    retry_queue_name,
)


@dataclass(frozen=True, slots=True)
class QueueMetrics:
    queue_name: str
    message_count: int
    consumer_count: int


def monitored_queue_names() -> tuple[str, ...]:
    names: list[str] = []

    for queue_name in QUEUE_NAMES:
        names.extend(
            (
                queue_name,
                retry_queue_name(queue_name),
                dead_letter_queue_name(queue_name),
            )
        )

    return tuple(names)


async def collect_queue_metrics(
    channel: AbstractRobustChannel,
) -> list[QueueMetrics]:
    snapshots: list[QueueMetrics] = []

    for queue_name in monitored_queue_names():
        queue = await channel.declare_queue(
            queue_name,
            passive=True,
            robust=False,
        )

        # Refresh passive declaration so RabbitMQ returns
        # the current message/consumer counts.
        declaration = await queue.declare()

        snapshots.append(
            QueueMetrics(
                queue_name=queue_name,
                message_count=(declaration.message_count),
                consumer_count=(declaration.consumer_count),
            )
        )

    return snapshots
