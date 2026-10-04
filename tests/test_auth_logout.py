from __future__ import annotations

from unittest.mock import AsyncMock

from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from redis.exceptions import RedisError

from app.main import create_app


def _configure_auth(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "KEYCLOAK_PUBLIC_URL",
        "http://localhost:8081",
    )

    monkeypatch.setenv(
        "KEYCLOAK_REALM",
        "whatsapp-platform",
    )

    monkeypatch.setenv(
        "KEYCLOAK_BFF_CLIENT_ID",
        "whatsapp-platform-bff",
    )

    monkeypatch.setenv(
        "AUTH_REDIRECT_URI",
        "http://localhost:8011/auth/callback",
    )

    monkeypatch.setenv(
        "AUTH_TRANSACTION_COOKIE_SECURE",
        "false",
    )

    monkeypatch.setenv(
        "AUTH_SESSION_COOKIE_SECURE",
        "false",
    )


def _create_test_client() -> tuple[
    TestClient,
    AsyncMock,
]:
    redis = AsyncMock()

    app = create_app()
    app.state.redis = redis

    return (
        TestClient(app),
        redis,
    )


def _session_deletion_header(
    response: object,
) -> str:
    headers = response.headers.get_list("set-cookie")

    matching = [header for header in headers if header.lower().startswith("wp_session=")]

    assert len(matching) == 1

    return matching[0].lower()


def test_logout_deletes_redis_session(
    monkeypatch: MonkeyPatch,
) -> None:
    _configure_auth(monkeypatch)

    client, redis = _create_test_client()

    client.cookies.set(
        "wp_session",
        "test-session-id",
    )

    response = client.post("/auth/logout")

    assert response.status_code == 204

    redis.delete.assert_awaited_once_with("wp:session:test-session-id")


def test_logout_deletes_session_cookie(
    monkeypatch: MonkeyPatch,
) -> None:
    _configure_auth(monkeypatch)

    client, _ = _create_test_client()

    client.cookies.set(
        "wp_session",
        "test-session-id",
    )

    response = client.post("/auth/logout")

    assert response.status_code == 204

    header = _session_deletion_header(response)

    assert "wp_session=" in header
    assert "max-age=0" in header
    assert "path=/" in header
    assert "httponly" in header
    assert "samesite=lax" in header


def test_logout_is_idempotent_without_session(
    monkeypatch: MonkeyPatch,
) -> None:
    _configure_auth(monkeypatch)

    client, redis = _create_test_client()

    response = client.post("/auth/logout")

    assert response.status_code == 204

    redis.delete.assert_not_awaited()

    header = _session_deletion_header(response)

    assert "max-age=0" in header


def test_logout_sets_no_store(
    monkeypatch: MonkeyPatch,
) -> None:
    _configure_auth(monkeypatch)

    client, _ = _create_test_client()

    client.cookies.set(
        "wp_session",
        "test-session-id",
    )

    response = client.post("/auth/logout")

    assert response.status_code == 204

    assert response.headers["cache-control"] == "no-store"


def test_logout_rejects_get_method(
    monkeypatch: MonkeyPatch,
) -> None:
    _configure_auth(monkeypatch)

    client, _ = _create_test_client()

    response = client.get("/auth/logout")

    assert response.status_code == 405


def test_logout_keeps_cookie_when_redis_fails(
    monkeypatch: MonkeyPatch,
) -> None:
    _configure_auth(monkeypatch)

    client, redis = _create_test_client()

    redis.delete.side_effect = RedisError("Redis unavailable")

    client.cookies.set(
        "wp_session",
        "test-session-id",
    )

    response = client.post("/auth/logout")

    assert response.status_code == 503

    assert response.json() == {"detail": ("Session service is unavailable.")}

    set_cookie_headers = response.headers.get_list("set-cookie")

    assert not any(header.lower().startswith("wp_session=") for header in set_cookie_headers)


def test_logout_does_not_expose_session_id(
    monkeypatch: MonkeyPatch,
) -> None:
    _configure_auth(monkeypatch)

    client, _ = _create_test_client()

    client.cookies.set(
        "wp_session",
        "secret-session-id",
    )

    response = client.post("/auth/logout")

    assert response.status_code == 204

    assert "secret-session-id" not in response.text
