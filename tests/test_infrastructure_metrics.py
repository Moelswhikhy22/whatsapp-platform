from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import (
    AsyncMock,
    MagicMock,
)

import pytest
from fastapi import Response
from prometheus_client import (
    CollectorRegistry,
)

from app.api import health as health_module
from app.api.health import readiness
from app.observability.metrics import (
    InfrastructureMetrics,
)


def test_dependency_metrics_record_up_and_down() -> None:
    registry = CollectorRegistry()

    metrics = InfrastructureMetrics(registry=registry)

    metrics.observe_dependency_health(
        postgres=True,
        redis=False,
        rabbitmq=True,
    )

    output = metrics.render_latest().decode("utf-8")

    assert 'whatsapp_platform_dependency_up{dependency="postgresql"} 1.0' in output

    assert 'whatsapp_platform_dependency_up{dependency="redis"} 0.0' in output

    assert 'whatsapp_platform_dependency_up{dependency="rabbitmq"} 1.0' in output


def test_dependency_metrics_count_health_checks() -> None:
    registry = CollectorRegistry()

    metrics = InfrastructureMetrics(registry=registry)

    metrics.observe_dependency_health(
        postgres=True,
        redis=False,
        rabbitmq=True,
    )

    output = metrics.render_latest().decode("utf-8")

    assert "whatsapp_platform_dependency_health_checks_total" in output

    assert 'dependency="redis",outcome="down"' in output

    assert 'dependency="postgresql",outcome="up"' in output


def test_readiness_metrics_record_status_and_duration() -> None:
    registry = CollectorRegistry()

    metrics = InfrastructureMetrics(registry=registry)

    metrics.observe_readiness(
        status="ready",
        duration_seconds=0.125,
    )

    output = metrics.render_latest().decode("utf-8")

    assert "whatsapp_platform_readiness_checks_total" in output

    assert 'status="ready"' in output

    assert "whatsapp_platform_readiness_check_duration_seconds_count" in output


@pytest.mark.asyncio
async def test_ready_endpoint_records_dependency_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observe_dependencies = MagicMock()

    observe_readiness = MagicMock()

    monkeypatch.setattr(
        health_module.infrastructure_metrics,
        "observe_dependency_health",
        observe_dependencies,
    )

    monkeypatch.setattr(
        health_module.infrastructure_metrics,
        "observe_readiness",
        observe_readiness,
    )

    checker = MagicMock()

    checker.check = AsyncMock(
        return_value=SimpleNamespace(
            postgres=True,
            redis=True,
            rabbitmq=True,
            required_dependencies_ready=True,
            all_dependencies_ready=True,
        )
    )

    response = Response()

    result = await readiness(
        response=response,
        health_checker=checker,
    )

    assert result.status == "ready"

    observe_dependencies.assert_called_once_with(
        postgres=True,
        redis=True,
        rabbitmq=True,
    )

    assert observe_readiness.call_args.kwargs["status"] == "ready"

    assert observe_readiness.call_args.kwargs["duration_seconds"] >= 0


@pytest.mark.asyncio
async def test_not_ready_endpoint_records_down_dependency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observe_dependencies = MagicMock()

    observe_readiness = MagicMock()

    monkeypatch.setattr(
        health_module.infrastructure_metrics,
        "observe_dependency_health",
        observe_dependencies,
    )

    monkeypatch.setattr(
        health_module.infrastructure_metrics,
        "observe_readiness",
        observe_readiness,
    )

    checker = MagicMock()

    checker.check = AsyncMock(
        return_value=SimpleNamespace(
            postgres=False,
            redis=True,
            rabbitmq=True,
            required_dependencies_ready=False,
            all_dependencies_ready=False,
        )
    )

    response = Response()

    result = await readiness(
        response=response,
        health_checker=checker,
    )

    assert result.status == "not_ready"

    assert response.status_code == 503

    observe_dependencies.assert_called_once_with(
        postgres=False,
        redis=True,
        rabbitmq=True,
    )

    assert observe_readiness.call_args.kwargs["status"] == "not_ready"
