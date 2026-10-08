from __future__ import annotations

import json
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from app.auth.config import TokenExchangeConfig
from app.auth.id_token import (
    HumanPrincipal,
    IdTokenJwksUnavailableError,
    InvalidIdTokenError,
)
from app.auth.token_exchange import OAuthTokenSet
from app.main import create_app


def _configure_auth(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "KEYCLOAK_PUBLIC_URL",
        "http://localhost:8081",
    )

    monkeypatch.setenv(
        "KEYCLOAK_INTERNAL_URL",
        "http://keycloak:8080",
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
        "KEYCLOAK_BFF_CLIENT_SECRET",
        "test-client-secret",
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

    # TestClient is deliberately not connected
    # to a real Redis instance in unit tests.
    app.state.redis = redis

    return (
        TestClient(app),
        redis,
    )


def _start_login(
    client: TestClient,
) -> str:
    response = client.get(
        "/auth/login",
        follow_redirects=False,
    )

    assert response.status_code == 302

    query = parse_qs(
        urlparse(
            response.headers["location"],
        ).query
    )

    return query["state"][0]


async def _successful_exchange(
    *,
    config: TokenExchangeConfig,
    code: str,
    code_verifier: str,
) -> OAuthTokenSet:
    del config
    del code
    del code_verifier

    return OAuthTokenSet(
        access_token="access-token",
        id_token="id-token",
        token_type="Bearer",
        expires_in=300,
        refresh_token="refresh-token",
        refresh_expires_in=1800,
        scope="openid profile email",
    )


def _mock_valid_identity(
    monkeypatch: MonkeyPatch,
) -> AsyncMock:
    validator = AsyncMock()

    validator.validate.return_value = HumanPrincipal(
        subject="keycloak-user-123",
    )

    monkeypatch.setattr(
        "app.api.auth.get_id_token_validator",
        lambda: validator,
    )

    return validator


def test_auth_callback_accepts_valid_transaction(
    monkeypatch: MonkeyPatch,
) -> None:
    _configure_auth(monkeypatch)

    monkeypatch.setattr(
        "app.api.auth.exchange_authorization_code",
        _successful_exchange,
    )

    validator = _mock_valid_identity(
        monkeypatch,
    )

    client, redis = _create_test_client()

    state = _start_login(client)

    nonce = client.cookies.get("wp_oauth_nonce")

    assert nonce is not None

    response = client.get(
        "/auth/callback",
        params={
            "code": "test-authorization-code",
            "state": state,
        },
    )

    assert response.status_code == 200

    assert response.json() == {"detail": "Authentication successful."}

    assert response.headers["cache-control"] == "no-store"

    validator.validate.assert_awaited_once_with(
        token="id-token",
        expected_nonce=nonce,
    )

    assert redis.set.await_count == 1

    session_id = client.cookies.get("wp_session")

    assert session_id is not None

    redis_call = redis.set.await_args

    assert redis_call.args[0] == (f"wp:session:{session_id}")

    assert redis_call.kwargs["ex"] == 28_800

    stored_session = json.loads(redis_call.args[1])

    assert stored_session["status"] == ("authenticated")

    assert stored_session["subject"] == ("keycloak-user-123")

    assert stored_session["id_token"] == ("id-token")


def test_auth_callback_rejects_invalid_id_token(
    monkeypatch: MonkeyPatch,
) -> None:
    _configure_auth(monkeypatch)

    monkeypatch.setattr(
        "app.api.auth.exchange_authorization_code",
        _successful_exchange,
    )

    validator = AsyncMock()

    validator.validate.side_effect = InvalidIdTokenError(
        "Invalid ID token.",
    )

    monkeypatch.setattr(
        "app.api.auth.get_id_token_validator",
        lambda: validator,
    )

    client, redis = _create_test_client()

    state = _start_login(client)

    response = client.get(
        "/auth/callback",
        params={
            "code": "test-code",
            "state": state,
        },
    )

    assert response.status_code == 401

    assert response.json() == {"detail": ("Identity token validation failed.")}

    redis.set.assert_not_awaited()

    assert client.cookies.get("wp_session") is None


def test_auth_callback_handles_jwks_unavailable(
    monkeypatch: MonkeyPatch,
) -> None:
    _configure_auth(monkeypatch)

    monkeypatch.setattr(
        "app.api.auth.exchange_authorization_code",
        _successful_exchange,
    )

    validator = AsyncMock()

    validator.validate.side_effect = IdTokenJwksUnavailableError(
        "JWKS unavailable.",
    )

    monkeypatch.setattr(
        "app.api.auth.get_id_token_validator",
        lambda: validator,
    )

    client, redis = _create_test_client()

    state = _start_login(client)

    response = client.get(
        "/auth/callback",
        params={
            "code": "test-code",
            "state": state,
        },
    )

    assert response.status_code == 503

    assert response.json() == {"detail": ("Authentication service is unavailable.")}

    redis.set.assert_not_awaited()

    assert client.cookies.get("wp_session") is None


def test_auth_callback_rejects_state_mismatch(
    monkeypatch: MonkeyPatch,
) -> None:
    _configure_auth(monkeypatch)

    client, redis = _create_test_client()

    _start_login(client)

    response = client.get(
        "/auth/callback",
        params={
            "code": "test-code",
            "state": "attacker-state",
        },
    )

    assert response.status_code == 400

    assert response.json() == {"detail": ("Invalid authentication state.")}

    assert response.headers["cache-control"] == "no-store"

    redis.set.assert_not_awaited()


def test_auth_callback_rejects_missing_transaction(
    monkeypatch: MonkeyPatch,
) -> None:
    _configure_auth(monkeypatch)

    client, redis = _create_test_client()

    response = client.get(
        "/auth/callback",
        params={
            "code": "test-code",
            "state": "test-state",
        },
    )

    assert response.status_code == 400

    assert response.json() == {"detail": ("Authentication transaction is missing or expired.")}

    assert response.headers["cache-control"] == "no-store"

    redis.set.assert_not_awaited()


def test_auth_callback_rejects_missing_code(
    monkeypatch: MonkeyPatch,
) -> None:
    _configure_auth(monkeypatch)

    client, redis = _create_test_client()

    state = _start_login(client)

    response = client.get(
        "/auth/callback",
        params={
            "state": state,
        },
    )

    assert response.status_code == 400

    assert response.json() == {"detail": ("Authorization code is missing.")}

    redis.set.assert_not_awaited()


def test_auth_callback_handles_provider_error(
    monkeypatch: MonkeyPatch,
) -> None:
    _configure_auth(monkeypatch)

    client, redis = _create_test_client()

    state = _start_login(client)

    response = client.get(
        "/auth/callback",
        params={
            "error": "access_denied",
            "state": state,
        },
    )

    assert response.status_code == 400

    assert response.json() == {"detail": ("Authorization was not completed.")}

    redis.set.assert_not_awaited()


def test_auth_callback_consumes_transaction_cookies(
    monkeypatch: MonkeyPatch,
) -> None:
    _configure_auth(monkeypatch)

    monkeypatch.setattr(
        "app.api.auth.exchange_authorization_code",
        _successful_exchange,
    )

    _mock_valid_identity(
        monkeypatch,
    )

    client, _ = _create_test_client()

    state = _start_login(client)

    assert client.cookies.get("wp_oauth_state") is not None

    assert client.cookies.get("wp_oauth_pkce_verifier") is not None

    assert client.cookies.get("wp_oauth_nonce") is not None

    response = client.get(
        "/auth/callback",
        params={
            "code": "test-code",
            "state": state,
        },
    )

    assert response.status_code == 200

    assert client.cookies.get("wp_oauth_state") is None

    assert client.cookies.get("wp_oauth_pkce_verifier") is None

    assert client.cookies.get("wp_oauth_nonce") is None

    assert client.cookies.get("wp_session") is not None


def test_auth_callback_consumes_cookies_on_state_mismatch(
    monkeypatch: MonkeyPatch,
) -> None:
    _configure_auth(monkeypatch)

    client, _ = _create_test_client()

    _start_login(client)

    response = client.get(
        "/auth/callback",
        params={
            "code": "test-code",
            "state": "wrong-state",
        },
    )

    assert response.status_code == 400

    assert client.cookies.get("wp_oauth_state") is None

    assert client.cookies.get("wp_oauth_pkce_verifier") is None

    assert client.cookies.get("wp_oauth_nonce") is None

    assert client.cookies.get("wp_session") is None


def test_auth_callback_does_not_expose_tokens(
    monkeypatch: MonkeyPatch,
) -> None:
    _configure_auth(monkeypatch)

    monkeypatch.setattr(
        "app.api.auth.exchange_authorization_code",
        _successful_exchange,
    )

    _mock_valid_identity(
        monkeypatch,
    )

    client, _ = _create_test_client()

    state = _start_login(client)

    response = client.get(
        "/auth/callback",
        params={
            "code": "test-code",
            "state": state,
        },
    )

    assert response.status_code == 200

    body = response.text

    assert "access-token" not in body
    assert "id-token" not in body
    assert "refresh-token" not in body


def test_auth_callback_session_cookie_matches_redis_key(
    monkeypatch: MonkeyPatch,
) -> None:
    _configure_auth(monkeypatch)

    monkeypatch.setattr(
        "app.api.auth.exchange_authorization_code",
        _successful_exchange,
    )

    _mock_valid_identity(
        monkeypatch,
    )

    client, redis = _create_test_client()

    state = _start_login(client)

    response = client.get(
        "/auth/callback",
        params={
            "code": "test-code",
            "state": state,
        },
    )

    assert response.status_code == 200

    session_id = client.cookies.get("wp_session")

    assert session_id is not None

    redis_call = redis.set.await_args

    session_key = redis_call.args[0]

    assert session_key == (f"wp:session:{session_id}")
