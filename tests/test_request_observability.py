from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest
from fastapi import (
    FastAPI,
    Request,
)

from app.middleware import (
    request_observability as module,
)
from app.middleware.request_observability import (
    request_observability_middleware,
)
from app.observability.context import (
    get_log_context,
)


@pytest.mark.asyncio
async def test_request_gets_server_generated_trace_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log_info = MagicMock()

    monkeypatch.setattr(
        module.logger,
        "info",
        log_info,
    )

    application = FastAPI()

    application.middleware("http")(request_observability_middleware)

    @application.get("/probe")
    async def probe(
        request: Request,
    ) -> dict[str, str | None]:
        request.state.observability_tenant_id = "tenant-123"

        return {"trace_id": (get_log_context().trace_id)}

    transport = httpx.ASGITransport(app=application)

    async with httpx.AsyncClient(
        transport=transport,
        base_url="https://example.com",
    ) as client:
        response = await client.get(
            "/probe",
            headers={
                "X-Request-ID": ("untrusted-client-id"),
            },
        )

    assert response.status_code == 200

    response_trace_id = response.headers["X-Request-ID"]

    assert response_trace_id

    assert response_trace_id != "untrusted-client-id"

    assert response.json()["trace_id"] == response_trace_id

    extra = log_info.call_args.kwargs["extra"]

    assert extra["trace_id"] == response_trace_id

    assert extra["tenant_id"] == "tenant-123"

    assert extra["status_code"] == 200


@pytest.mark.asyncio
async def test_request_log_does_not_include_query_string(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log_info = MagicMock()

    monkeypatch.setattr(
        module.logger,
        "info",
        log_info,
    )

    application = FastAPI()

    application.middleware("http")(request_observability_middleware)

    @application.get("/probe")
    async def probe() -> dict[str, bool]:
        return {
            "ok": True,
        }

    transport = httpx.ASGITransport(app=application)

    async with httpx.AsyncClient(
        transport=transport,
        base_url="https://example.com",
    ) as client:
        response = await client.get(
            "/probe",
            params={
                "access_token": ("super-secret"),
            },
        )

    assert response.status_code == 200

    extra = log_info.call_args.kwargs["extra"]

    assert extra["path"] == "/probe"

    assert "super-secret" not in str(extra)

    assert "access_token" not in str(extra)


@pytest.mark.asyncio
async def test_request_context_is_reset_after_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        module.logger,
        "info",
        MagicMock(),
    )

    application = FastAPI()

    application.middleware("http")(request_observability_middleware)

    @application.get("/probe")
    async def probe() -> dict[str, bool]:
        assert get_log_context().trace_id is not None

        return {
            "ok": True,
        }

    transport = httpx.ASGITransport(app=application)

    async with httpx.AsyncClient(
        transport=transport,
        base_url="https://example.com",
    ) as client:
        response = await client.get("/probe")

    assert response.status_code == 200

    context = get_log_context()

    assert context.trace_id is None
    assert context.tenant_id is None


@pytest.mark.asyncio
async def test_failed_request_is_logged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log_exception = MagicMock()

    monkeypatch.setattr(
        module.logger,
        "exception",
        log_exception,
    )

    application = FastAPI()

    application.middleware("http")(request_observability_middleware)

    @application.get("/failure")
    async def failure() -> None:
        raise RuntimeError("boom")

    transport = httpx.ASGITransport(
        app=application,
        raise_app_exceptions=True,
    )

    async with httpx.AsyncClient(
        transport=transport,
        base_url="https://example.com",
    ) as client:
        with pytest.raises(RuntimeError):
            await client.get("/failure")

    extra = log_exception.call_args.kwargs["extra"]

    assert extra["status_code"] == 500

    assert extra["outcome"] == "failure"

    assert extra["path"] == "/failure"


@pytest.mark.asyncio
async def test_request_log_contains_duration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log_info = MagicMock()

    monkeypatch.setattr(
        module.logger,
        "info",
        log_info,
    )

    application = FastAPI()

    application.middleware("http")(request_observability_middleware)

    @application.get("/duration")
    async def duration() -> dict[str, bool]:
        return {
            "ok": True,
        }

    transport = httpx.ASGITransport(app=application)

    async with httpx.AsyncClient(
        transport=transport,
        base_url="https://example.com",
    ) as client:
        response = await client.get("/duration")

    assert response.status_code == 200

    extra = log_info.call_args.kwargs["extra"]

    assert isinstance(
        extra["duration_ms"],
        float,
    )

    assert extra["duration_ms"] >= 0
