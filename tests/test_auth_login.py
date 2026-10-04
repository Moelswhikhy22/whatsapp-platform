from __future__ import annotations

from urllib.parse import (
    parse_qs,
    urlparse,
)

from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from app.auth.pkce import (
    create_code_challenge,
)
from app.main import create_app


def test_auth_login_redirects_to_keycloak(
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

    client = TestClient(create_app())

    response = client.get(
        "/auth/login",
        follow_redirects=False,
    )

    assert response.status_code == 302

    location = response.headers["location"]

    parsed = urlparse(location)
    query = parse_qs(parsed.query)

    assert parsed.scheme == "http"
    assert parsed.netloc == "localhost:8081"

    assert parsed.path == ("/realms/whatsapp-platform/protocol/openid-connect/auth")

    assert query["client_id"] == ["whatsapp-platform-bff"]

    assert query["response_type"] == ["code"]

    assert query["redirect_uri"] == ["http://localhost:8011/auth/callback"]

    assert query["code_challenge_method"] == ["S256"]

    state = response.cookies["wp_oauth_state"]

    verifier = response.cookies["wp_oauth_pkce_verifier"]

    nonce = response.cookies["wp_oauth_nonce"]

    assert query["state"] == [state]
    assert query["nonce"] == [nonce]

    assert query["code_challenge"] == [create_code_challenge(verifier)]

    def test_auth_login_uses_protected_transaction_cookies(
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

        client = TestClient(create_app())

        response = client.get(
            "/auth/login",
            follow_redirects=False,
        )

        set_cookie = response.headers.get_list("set-cookie")

        assert len(set_cookie) == 3

        for cookie in set_cookie:
            lowered = cookie.lower()

            assert "httponly" in lowered
            assert "samesite=lax" in lowered
            assert "max-age=300" in lowered
