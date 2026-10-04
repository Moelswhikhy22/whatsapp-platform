from __future__ import annotations

import base64
from urllib.parse import parse_qs

import httpx
import pytest

from app.auth.config import TokenExchangeConfig
from app.auth.token_exchange import (
    InvalidTokenResponseError,
    TokenExchangeRejectedError,
    TokenExchangeUnavailableError,
    exchange_authorization_code,
)


def _config() -> TokenExchangeConfig:
    return TokenExchangeConfig(
        keycloak_internal_url="http://keycloak:8080",
        keycloak_realm="whatsapp-platform",
        client_id="whatsapp-platform-bff",
        client_secret="test-client-secret",
        redirect_uri="http://localhost:8011/auth/callback",
        timeout_seconds=10.0,
    )


@pytest.mark.asyncio
async def test_exchange_authorization_code() -> None:
    async def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        assert request.url == (
            "http://keycloak:8080/realms/whatsapp-platform/protocol/openid-connect/token"
        )

        authorization = request.headers["authorization"]

        scheme, encoded = authorization.split(
            " ",
            maxsplit=1,
        )

        assert scheme == "Basic"

        credentials = base64.b64decode(encoded).decode("utf-8")

        assert credentials == ("whatsapp-platform-bff:test-client-secret")

        form = parse_qs(request.content.decode("utf-8"))

        assert form["grant_type"] == ["authorization_code"]

        assert form["code"] == ["authorization-code"]

        assert form["code_verifier"] == ["pkce-verifier"]

        assert form["redirect_uri"] == ["http://localhost:8011/auth/callback"]

        return httpx.Response(
            200,
            json={
                "access_token": "access-token",
                "id_token": "id-token",
                "refresh_token": "refresh-token",
                "token_type": "Bearer",
                "expires_in": 300,
                "refresh_expires_in": 1800,
                "scope": "openid profile email",
            },
        )

    transport = httpx.MockTransport(handler)

    async with httpx.AsyncClient(
        transport=transport,
    ) as client:
        tokens = await exchange_authorization_code(
            config=_config(),
            code="authorization-code",
            code_verifier="pkce-verifier",
            client=client,
        )

    assert tokens.access_token == "access-token"
    assert tokens.id_token == "id-token"
    assert tokens.refresh_token == "refresh-token"
    assert tokens.token_type == "Bearer"
    assert tokens.expires_in == 300


@pytest.mark.asyncio
async def test_exchange_rejects_invalid_code() -> None:
    async def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        return httpx.Response(
            400,
            json={
                "error": "invalid_grant",
            },
        )

    transport = httpx.MockTransport(handler)

    async with httpx.AsyncClient(
        transport=transport,
    ) as client:
        with pytest.raises(TokenExchangeRejectedError):
            await exchange_authorization_code(
                config=_config(),
                code="bad-code",
                code_verifier="verifier",
                client=client,
            )


@pytest.mark.asyncio
async def test_exchange_handles_provider_failure() -> None:
    async def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        return httpx.Response(
            503,
        )

    transport = httpx.MockTransport(handler)

    async with httpx.AsyncClient(
        transport=transport,
    ) as client:
        with pytest.raises(TokenExchangeUnavailableError):
            await exchange_authorization_code(
                config=_config(),
                code="code",
                code_verifier="verifier",
                client=client,
            )


@pytest.mark.asyncio
async def test_exchange_rejects_invalid_token_response() -> None:
    async def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "access_token": "access-token",
                "token_type": "Bearer",
                "expires_in": 300,
            },
        )

    transport = httpx.MockTransport(handler)

    async with httpx.AsyncClient(
        transport=transport,
    ) as client:
        with pytest.raises(InvalidTokenResponseError):
            await exchange_authorization_code(
                config=_config(),
                code="code",
                code_verifier="verifier",
                client=client,
            )
