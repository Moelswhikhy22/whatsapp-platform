from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest
from fastapi import FastAPI

from prometheus_client import (
    CollectorRegistry,
)

from app.middleware import (
    request_observability as middleware_module,
)
from app.middleware.request_observability import (
    request_observability_middleware,
)
from app.observability.metrics import (
    ApiMetrics,
)


def test_api_metrics_records_request() -> None:
    registry = CollectorRegistry()

    metrics = ApiMetrics(registry=registry)

    metrics.observe_http_request(
        method="GET",
        route="/api/v1/items/{item_id}",
        status_code=200,
        duration_seconds=0.125,
    )

    output = metrics.render_latest().decode("utf-8")

    assert "whatsapp_platform_http_requests_total" in output

    assert 'method="GET"' in output

    assert 'route="/api/v1/items/{item_id}"' in output

    assert 'status="200"' in output

    assert "whatsapp_platform_http_request_duration_seconds_count" in output


def test_api_metrics_do_not_include_tenant_label() -> None:
    registry = CollectorRegistry()

    metrics = ApiMetrics(registry=registry)

    metrics.observe_http_request(
        method="POST",
        route="/api/v1/messages",
        status_code=201,
        duration_seconds=0.05,
    )

    output = metrics.render_latest().decode("utf-8")

    assert "tenant_id=" not in output


@pytest.mark.asyncio
async def test_middleware_uses_route_template_for_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observe = MagicMock()

    monkeypatch.setattr(
        middleware_module.api_metrics,
        "observe_http_request",
        observe,
    )

    monkeypatch.setattr(
        middleware_module.logger,
        "info",
        MagicMock(),
    )

    application = FastAPI()

    application.middleware("http")(request_observability_middleware)

    @application.get("/items/{item_id}")
    async def get_item(
        item_id: str,
    ) -> dict[str, str]:
        return {
            "id": item_id,
        }

    transport = httpx.ASGITransport(app=application)

    async with httpx.AsyncClient(
        transport=transport,
        base_url="https://example.com",
    ) as client:
        response = await client.get("/items/customer-123")

    assert response.status_code == 200

    observe.assert_called_once()

    call = observe.call_args.kwargs

    assert call["route"] == "/items/{item_id}"

    assert "customer-123" not in call["route"]

    assert call["method"] == "GET"
    assert call["status_code"] == 200


@pytest.mark.asyncio
async def test_unmatched_path_uses_bounded_metric_label(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observe = MagicMock()

    monkeypatch.setattr(
        middleware_module.api_metrics,
        "observe_http_request",
        observe,
    )

    monkeypatch.setattr(
        middleware_module.logger,
        "info",
        MagicMock(),
    )

    application = FastAPI()

    application.middleware("http")(request_observability_middleware)

    transport = httpx.ASGITransport(app=application)

    async with httpx.AsyncClient(
        transport=transport,
        base_url="https://example.com",
    ) as client:
        response = await client.get("/unknown/random-resource-123")

    assert response.status_code == 404

    call = observe.call_args.kwargs

    assert call["route"] == "unmatched"


@pytest.mark.asyncio
async def test_metrics_endpoint_is_not_self_instrumented(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observe = MagicMock()

    monkeypatch.setattr(
        middleware_module.api_metrics,
        "observe_http_request",
        observe,
    )

    monkeypatch.setattr(
        middleware_module.logger,
        "info",
        MagicMock(),
    )

    application = FastAPI()

    application.middleware("http")(request_observability_middleware)

    @application.get("/metrics")
    async def metrics() -> str:
        return "metrics"

    transport = httpx.ASGITransport(app=application)

    async with httpx.AsyncClient(
        transport=transport,
        base_url="https://example.com",
    ) as client:
        response = await client.get("/metrics")

    assert response.status_code == 200

    observe.assert_not_called()
