from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass

from app.integrations.rabbitmq.client import (
    RabbitMQClient,
)
from app.integrations.rabbitmq.topology import (
    QUEUE_NAMES,
    dead_letter_queue_name,
    retry_queue_name,
)
from app.observability.metrics import (
    RabbitMQQueueMetrics,
    rabbitmq_queue_metrics,
)


@dataclass(
    frozen=True,
    slots=True,
)
class QueueMetricSpec:
    name: str
    kind: str
    warning_threshold: int
    critical_threshold: int


def monitored_queue_specs() -> tuple[QueueMetricSpec, ...]:
    primary_warning = _positive_int_env(
        "RABBITMQ_QUEUE_WARNING_DEPTH",
        100,
    )

    primary_critical = _positive_int_env(
        "RABBITMQ_QUEUE_CRITICAL_DEPTH",
        1000,
    )

    retry_warning = _positive_int_env(
        "RABBITMQ_RETRY_QUEUE_WARNING_DEPTH",
        25,
    )

    retry_critical = _positive_int_env(
        "RABBITMQ_RETRY_QUEUE_CRITICAL_DEPTH",
        100,
    )

    dead_warning = _positive_int_env(
        "RABBITMQ_DLQ_WARNING_DEPTH",
        1,
    )

    dead_critical = _positive_int_env(
        "RABBITMQ_DLQ_CRITICAL_DEPTH",
        10,
    )

    _validate_thresholds(
        "primary",
        primary_warning,
        primary_critical,
    )

    _validate_thresholds(
        "retry",
        retry_warning,
        retry_critical,
    )

    _validate_thresholds(
        "dead",
        dead_warning,
        dead_critical,
    )

    specs: list[QueueMetricSpec] = []

    for queue_name in QUEUE_NAMES:
        specs.extend(
            [
                QueueMetricSpec(
                    name=queue_name,
                    kind="primary",
                    warning_threshold=(primary_warning),
                    critical_threshold=(primary_critical),
                ),
                QueueMetricSpec(
                    name=(retry_queue_name(queue_name)),
                    kind="retry",
                    warning_threshold=(retry_warning),
                    critical_threshold=(retry_critical),
                ),
                QueueMetricSpec(
                    name=(dead_letter_queue_name(queue_name)),
                    kind="dead",
                    warning_threshold=(dead_warning),
                    critical_threshold=(dead_critical),
                ),
            ]
        )

    return tuple(specs)


class RabbitMQQueueCollector:
    def __init__(
        self,
        *,
        client: RabbitMQClient,
        metrics: RabbitMQQueueMetrics = (rabbitmq_queue_metrics),
    ) -> None:
        self._client = client
        self._metrics = metrics
        self._lock = asyncio.Lock()

    @classmethod
    def from_environment(
        cls,
    ) -> RabbitMQQueueCollector | None:
        rabbitmq_url = os.getenv("RABBITMQ_URL")

        if rabbitmq_url is None or not rabbitmq_url.strip():
            return None

        return cls(client=RabbitMQClient(rabbitmq_url.strip()))

    async def collect(
        self,
    ) -> bool:
        async with self._lock:
            try:
                await self._client.connect()

                channel = await self._client.open_channel()

                try:
                    for spec in monitored_queue_specs():
                        queue = await channel.declare_queue(
                            spec.name,
                            passive=True,
                            robust=False,
                        )

                        result = await queue.declare()

                        message_count = int(
                            getattr(
                                result,
                                "message_count",
                                0,
                            )
                            or 0
                        )

                        consumer_count = int(
                            getattr(
                                result,
                                "consumer_count",
                                0,
                            )
                            or 0
                        )

                        self._metrics.observe_queue(
                            queue_name=spec.name,
                            kind=spec.kind,
                            message_count=(message_count),
                            consumer_count=(consumer_count),
                            warning_threshold=(spec.warning_threshold),
                            critical_threshold=(spec.critical_threshold),
                        )

                finally:
                    await channel.close()

            except Exception:
                self._metrics.observe_collection_failure()

                return False

            self._metrics.observe_collection_success()

            return True

    async def close(
        self,
    ) -> None:
        await self._client.close()


def _positive_int_env(
    name: str,
    default: int,
) -> int:
    raw_value = os.getenv(name)

    if raw_value is None:
        return default

    normalized = raw_value.strip()

    try:
        value = int(normalized)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer.") from exc

    if value <= 0:
        raise ValueError(f"{name} must be greater than zero.")

    return value


def _validate_thresholds(
    kind: str,
    warning: int,
    critical: int,
) -> None:
    if critical < warning:
        raise ValueError(
            "RabbitMQ "
            f"{kind} critical threshold "
            "must be greater than or equal "
            "to its warning threshold."
        )
