from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import (
    AsyncMock,
    MagicMock,
)

import pytest
from fastapi import (
    HTTPException,
    Request,
)

import app.api.dependencies.human_auth as human_auth
from app.auth.session_cookie import (
    SESSION_COOKIE_NAME,
)
from app.auth.session_store import (
    RedisSessionStore,
    SessionStorageError,
)


def _request() -> Request:
    app = MagicMock()
    app.state = SimpleNamespace(
        redis=MagicMock(),
    )

    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/test",
            "query_string": b"",
            "headers": [
                (
                    b"cookie",
                    (f"{SESSION_COOKIE_NAME}=session-123").encode(),
                )
            ],
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
async def test_redis_session_failure_never_authenticates_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        human_auth,
        "load_session_cookie_config",
        lambda: SimpleNamespace(
            max_age_seconds=3600,
        ),
    )

    monkeypatch.setattr(
        RedisSessionStore,
        "get",
        AsyncMock(side_effect=SessionStorageError("redis unavailable")),
    )

    if hasattr(
        human_auth,
        "record_security_access",
    ):
        monkeypatch.setattr(
            human_auth,
            "record_security_access",
            AsyncMock(),
        )

    with pytest.raises(HTTPException) as exc_info:
        await human_auth.require_authenticated_session(_request())

    assert exc_info.value.status_code == 503
