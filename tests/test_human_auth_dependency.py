from __future__ import annotations

from typing import Annotated
from unittest.mock import AsyncMock

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from redis.exceptions import RedisError

from app.api.dependencies.human_auth import (
    require_human_principal,
)
from app.auth.id_token import HumanPrincipal
from app.auth.session_cookie import (
    SESSION_COOKIE_NAME,
)
from app.auth.session_store import SessionRecord


def _session(
    *,
    status: str = "authenticated",
    subject: str | None = "keycloak-user-123",
) -> str:
    record = SessionRecord(
        status=status,  # type: ignore[arg-type]
        access_token="access-token",
        id_token="id-token",
        refresh_token="refresh-token",
        token_type="Bearer",
        expires_in=300,
        refresh_expires_in=1800,
        scope="openid profile email",
        nonce="nonce",
        subject=subject,
    )

    return record.to_json()


def _create_client() -> tuple[
    TestClient,
    AsyncMock,
]:
    app = FastAPI()

    redis = AsyncMock()

    app.state.redis = redis

    @app.get("/protected")
    async def protected(
        principal: Annotated[
            HumanPrincipal,
            Depends(require_human_principal),
        ],
    ) -> dict[str, str]:
        return {
            "subject": principal.subject,
        }

    return TestClient(app), redis


def test_authenticated_session_returns_principal() -> None:
    client, redis = _create_client()

    redis.get.return_value = _session()

    client.cookies.set(
        SESSION_COOKIE_NAME,
        "test-session",
    )

    response = client.get("/protected")

    assert response.status_code == 200

    assert response.json() == {"subject": "keycloak-user-123"}

    redis.get.assert_awaited_once_with("wp:session:test-session")


def test_missing_session_cookie_returns_401() -> None:
    client, redis = _create_client()

    response = client.get("/protected")

    assert response.status_code == 401

    assert response.json() == {"detail": "Authentication is required."}

    redis.get.assert_not_awaited()


def test_missing_redis_session_returns_401() -> None:
    client, redis = _create_client()

    redis.get.return_value = None

    client.cookies.set(
        SESSION_COOKIE_NAME,
        "expired-session",
    )

    response = client.get("/protected")

    assert response.status_code == 401

    assert response.json() == {"detail": "Session is invalid or expired."}


def test_pending_session_returns_401() -> None:
    client, redis = _create_client()

    redis.get.return_value = _session(
        status="pending_validation",
    )

    client.cookies.set(
        SESSION_COOKIE_NAME,
        "pending-session",
    )

    response = client.get("/protected")

    assert response.status_code == 401

    assert response.json() == {"detail": "Session is not authenticated."}


def test_authenticated_session_without_subject_returns_401() -> None:
    client, redis = _create_client()

    redis.get.return_value = _session(
        subject=None,
    )

    client.cookies.set(
        SESSION_COOKIE_NAME,
        "invalid-session",
    )

    response = client.get("/protected")

    assert response.status_code == 401

    assert response.json() == {"detail": "Session identity is invalid."}


def test_redis_failure_returns_503() -> None:
    client, redis = _create_client()

    redis.get.side_effect = RedisError("Redis unavailable.")

    client.cookies.set(
        SESSION_COOKIE_NAME,
        "test-session",
    )

    response = client.get("/protected")

    assert response.status_code == 503

    assert response.json() == {"detail": "Session service is unavailable."}
