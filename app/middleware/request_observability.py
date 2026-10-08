from __future__ import annotations

import logging
from collections.abc import (
    Awaitable,
    Callable,
)
from time import perf_counter
from uuid import uuid4

from fastapi import Request, Response

from app.observability.context import (
    bind_log_context,
    reset_log_context,
)
from app.observability.logging import (
    JsonLogFormatter,
)
from app.observability.metrics import (
    api_metrics,
)


_LOGGER_NAME = "whatsapp_platform.http"

_HANDLER_NAME = "whatsapp-platform-http-json"


def _build_logger() -> logging.Logger:
    logger = logging.getLogger(_LOGGER_NAME)

    logger.setLevel(logging.INFO)

    has_json_handler = any(handler.get_name() == _HANDLER_NAME for handler in logger.handlers)

    if not has_json_handler:
        handler = logging.StreamHandler()

        handler.set_name(_HANDLER_NAME)

        handler.setFormatter(JsonLogFormatter())

        logger.addHandler(handler)

    logger.propagate = False

    return logger


logger = _build_logger()


async def request_observability_middleware(
    request: Request,
    call_next: Callable[
        [Request],
        Awaitable[Response],
    ],
) -> Response:
    trace_id = uuid4().hex

    request.state.trace_id = trace_id

    context_tokens = bind_log_context(
        trace_id=trace_id,
    )

    started_at = perf_counter()

    try:
        response = await call_next(request)

    except Exception:
        duration_seconds = _duration_seconds(started_at)

        _record_request_metrics(
            request=request,
            status_code=500,
            duration_seconds=(duration_seconds),
        )

        logger.exception(
            "HTTP request failed.",
            extra={
                "event": "http.request",
                "component": "api",
                "outcome": "failure",
                "method": request.method,
                "path": request.url.path,
                "status_code": 500,
                "duration_ms": (_duration_ms(duration_seconds)),
                "trace_id": trace_id,
                "tenant_id": (_request_tenant_id(request)),
            },
        )

        raise

    else:
        duration_seconds = _duration_seconds(started_at)

        response.headers["X-Request-ID"] = trace_id

        _record_request_metrics(
            request=request,
            status_code=(response.status_code),
            duration_seconds=(duration_seconds),
        )

        logger.info(
            "HTTP request completed.",
            extra={
                "event": "http.request",
                "component": "api",
                "outcome": (_request_outcome(response.status_code)),
                "method": request.method,
                "path": request.url.path,
                "status_code": (response.status_code),
                "duration_ms": (_duration_ms(duration_seconds)),
                "trace_id": trace_id,
                "tenant_id": (_request_tenant_id(request)),
            },
        )

        return response

    finally:
        reset_log_context(context_tokens)


def _record_request_metrics(
    *,
    request: Request,
    status_code: int,
    duration_seconds: float,
) -> None:
    # Do not count Prometheus scrapes
    # themselves.
    if request.url.path == "/metrics":
        return

    api_metrics.observe_http_request(
        method=request.method,
        route=_route_template(request),
        status_code=status_code,
        duration_seconds=(duration_seconds),
    )


def _route_template(
    request: Request,
) -> str:
    route = request.scope.get("route")

    route_path = getattr(
        route,
        "path",
        None,
    )

    if (
        isinstance(
            route_path,
            str,
        )
        and route_path
    ):
        return route_path

    # Never fall back to request.url.path:
    # an unknown/raw URL may contain IDs or
    # attacker-controlled high-cardinality
    # values.
    return "unmatched"


def _request_tenant_id(
    request: Request,
) -> str | None:
    value = getattr(
        request.state,
        "observability_tenant_id",
        None,
    )

    if value is None:
        return None

    normalized = str(value).strip()

    return normalized or None


def _duration_seconds(
    started_at: float,
) -> float:
    return max(
        perf_counter() - started_at,
        0.0,
    )


def _duration_ms(
    duration_seconds: float,
) -> float:
    return round(
        duration_seconds * 1000,
        3,
    )


def _request_outcome(
    status_code: int,
) -> str:
    if status_code >= 500:
        return "failure"

    if status_code >= 400:
        return "client_error"

    return "success"
    return "success"
