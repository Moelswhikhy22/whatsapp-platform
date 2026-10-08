from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import (
    BaseHTTPMiddleware,
)

from app.auth.session_cookie import (
    SESSION_COOKIE_NAME,
)
from app.rate_limit import (
    RateLimitBackendUnavailableError,
)
from app.session_rate_limit import (
    HumanSessionRateLimiter,
)


def _is_rate_limited_api_path(
    request: Request,
) -> bool:
    return request.url.path.startswith(
        "/api/"
    )


async def enforce_human_session_rate_limit(
    request: Request,
) -> Response | None:
    # Auth endpoints such as /auth/logout must remain
    # reachable even when Redis rate-limit protection
    # is unavailable. They do not grant authorization.
    if not _is_rate_limited_api_path(
        request
    ):
        return None

    session_id = request.cookies.get(
        SESSION_COOKIE_NAME
    )

    if not session_id:
        return None

    redis = getattr(
        request.app.state,
        "redis",
        None,
    )

    if redis is None:
        return _backend_unavailable_response()

    try:
        decision = await HumanSessionRateLimiter(
            redis
        ).check(
            session_id=session_id,
        )
    except (
        RateLimitBackendUnavailableError,
        RuntimeError,
    ):
        return _backend_unavailable_response()

    if decision.allowed:
        return None

    return JSONResponse(
        status_code=429,
        content={
            "detail": {
                "code": "SESSION_RATE_LIMIT_EXCEEDED",
                "message": "Too many session requests.",
            }
        },
        headers={
            "Retry-After": str(
                decision.retry_after_seconds
            )
        },
    )


class HumanSessionRateLimitMiddleware(
    BaseHTTPMiddleware
):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[
            [Request],
            Awaitable[Response],
        ],
    ) -> Response:
        limited_response = (
            await enforce_human_session_rate_limit(
                request
            )
        )

        if limited_response is not None:
            return limited_response

        return await call_next(
            request
        )


def _backend_unavailable_response() -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "detail": {
                "code": (
                    "SESSION_RATE_LIMIT_BACKEND_UNAVAILABLE"
                ),
                "message": (
                    "Session protection service "
                    "is unavailable."
                ),
            }
        },
    )
