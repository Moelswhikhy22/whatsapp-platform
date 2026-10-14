from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import (
    AsyncMock,
    MagicMock,
)

import pytest
from prometheus_client import (
    CollectorRegistry,
)

from app.integrations.rabbitmq.client import (
    RabbitMQClient,
)
from app.integrations.rabbitmq.topology import (
    QUEUE_NAMES,
)
from app.observability.metrics import (
    RabbitMQQueueMetrics,
)
from app.observability.rabbitmq_queues import (
    RabbitMQQueueCollector,
    monitored_queue_specs,
)


def test_monitored_queue_specs_cover_primary_retry_and_dead() -> None:
    specs = monitored_queue_specs()

    assert len(specs) == (len(QUEUE_NAMES) * 3)

    kinds = {spec.kind for spec in specs}

    assert kinds == {
        "primary",
        "retry",
        "dead",
    }

    names = {spec.name for spec in specs}

    assert "meta.inbound" in names
    assert "meta.inbound.retry" in names
    assert "meta.inbound.dead" in names

    assert "webhook.delivery" in names
    assert "webhook.delivery.retry" in names
    assert "webhook.delivery.dead" in names


def test_queue_depth_metrics_set_warning_and_critical() -> None:
    registry = CollectorRegistry()

    metrics = RabbitMQQueueMetrics(registry=registry)

    metrics.observe_queue(
        queue_name="meta.inbound",
        kind="primary",
        message_count=150,
        consumer_count=2,
        warning_threshold=100,
        critical_threshold=1000,
    )

    output = metrics.render_latest().decode("utf-8")

    assert 'queue="meta.inbound"' in output

    assert 'kind="primary"' in output

    assert "whatsapp_platform_rabbitmq_queue_messages" in output

    assert 'severity="warning"} 1.0' in output

    assert 'severity="critical"} 0.0' in output


@pytest.mark.asyncio
async def test_collector_reads_all_monitored_queues() -> None:
    registry = CollectorRegistry()

    metrics = RabbitMQQueueMetrics(registry=registry)

    client = MagicMock(spec=RabbitMQClient)

    client.connect = AsyncMock()

    queue = MagicMock()

    queue.declare = AsyncMock(
        return_value=SimpleNamespace(
            message_count=12,
            consumer_count=3,
        )
    )

    channel = MagicMock()

    channel.declare_queue = AsyncMock(return_value=queue)

    channel.close = AsyncMock()

    client.open_channel = AsyncMock(return_value=channel)

    client.close = AsyncMock()

    collector = RabbitMQQueueCollector(
        client=client,
        metrics=metrics,
    )

    result = await collector.collect()

    assert result is True

    assert channel.declare_queue.await_count == len(QUEUE_NAMES) * 3

    client.connect.assert_awaited_once()

    client.open_channel.assert_awaited_once()

    channel.close.assert_awaited_once()

    output = metrics.render_latest().decode("utf-8")

    assert "whatsapp_platform_rabbitmq_queue_collection_up 1.0" in output


@pytest.mark.asyncio
async def test_collector_failure_is_exposed_as_metric() -> None:
    registry = CollectorRegistry()

    metrics = RabbitMQQueueMetrics(registry=registry)

    client = MagicMock(spec=RabbitMQClient)

    client.connect = AsyncMock(side_effect=RuntimeError("rabbit unavailable"))

    client.close = AsyncMock()

    collector = RabbitMQQueueCollector(
        client=client,
        metrics=metrics,
    )

    result = await collector.collect()

    assert result is False

    output = metrics.render_latest().decode("utf-8")

    assert "whatsapp_platform_rabbitmq_queue_collection_up 0.0" in output

    assert "whatsapp_platform_rabbitmq_queue_collection_failures_total 1.0" in output
