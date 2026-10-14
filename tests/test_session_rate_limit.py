from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import (
    AsyncMock,
    MagicMock,
)

import pytest
from fastapi import Request
from redis.asyncio import Redis

from app.auth.session_cookie import (
    SESSION_COOKIE_NAME,
)
from app.middleware.session_rate_limit import (
    enforce_human_session_rate_limit,
)
from app.rate_limit import (
    RateLimitDecision,
)
from app.session_rate_limit import (
    HumanSessionRateLimiter,
)


def _request(
    *,
    path: str = "/api/v1/test",
    session_id: str | None,
    redis: object | None,
) -> Request:
    app = MagicMock()
    app.state = SimpleNamespace(
        redis=redis,
    )

    headers: list[tuple[bytes, bytes]] = []

    if session_id is not None:
        headers.append(
            (
                b"cookie",
                (f"{SESSION_COOKIE_NAME}={session_id}").encode(),
            )
        )

    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "query_string": b"",
            "headers": headers,
            "client": (
                "127.0.0.1",
                50000,
            ),
            "server": (
                "tenant-a.example.com",
                443,
            ),
            "scheme": "https",
            "app": app,
        }
    )


@pytest.mark.asyncio
async def test_session_rate_limit_skips_anonymous_request() -> None:
    response = await enforce_human_session_rate_limit(
        _request(
            session_id=None,
            redis=None,
        )
    )

    assert response is None


@pytest.mark.asyncio
async def test_session_rate_limit_skips_logout() -> None:
    response = await enforce_human_session_rate_limit(
        _request(
            path="/auth/logout",
            session_id="session-123",
            redis=None,
        )
    )

    assert response is None


@pytest.mark.asyncio
async def test_session_rate_limit_skips_auth_callback() -> None:
    response = await enforce_human_session_rate_limit(
        _request(
            path="/auth/callback",
            session_id="session-123",
            redis=None,
        )
    )

    assert response is None


@pytest.mark.asyncio
async def test_session_rate_limit_fails_closed_for_api_when_redis_missing() -> None:
    response = await enforce_human_session_rate_limit(
        _request(
            session_id="session-123",
            redis=None,
        )
    )

    assert response is not None
    assert response.status_code == 503


@pytest.mark.asyncio
async def test_session_rate_limit_returns_429_when_exceeded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    check = AsyncMock(
        return_value=RateLimitDecision(
            allowed=False,
            limit=300,
            remaining=0,
            retry_after_seconds=9,
        )
    )

    monkeypatch.setattr(
        HumanSessionRateLimiter,
        "check",
        check,
    )

    response = await enforce_human_session_rate_limit(
        _request(
            session_id="session-123",
            redis=MagicMock(
                spec=Redis,
            ),
        )
    )

    assert response is not None
    assert response.status_code == 429
    assert response.headers["retry-after"] == "9"


@pytest.mark.asyncio
async def test_session_rate_limiter_does_not_expose_session_id_in_key() -> None:
    redis = AsyncMock(
        spec=Redis,
    )

    redis.eval = AsyncMock(
        return_value=[
            1,
            60,
        ]
    )

    await HumanSessionRateLimiter(redis).check(
        session_id="super-secret-session-id",
    )

    key = redis.eval.await_args.args[2]

    assert "super-secret-session-id" not in key

    assert key.startswith("global:rate_limit:human_session:")
