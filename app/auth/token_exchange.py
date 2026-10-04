from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote

import httpx

from app.auth.config import TokenExchangeConfig


class TokenExchangeError(RuntimeError):
    """Base error for authorization-code exchange failures."""


class TokenExchangeRejectedError(TokenExchangeError):
    """Keycloak rejected the authorization-code exchange."""


class TokenExchangeUnavailableError(TokenExchangeError):
    """Keycloak could not be reached or returned a server error."""


class InvalidTokenResponseError(TokenExchangeError):
    """Keycloak returned an invalid token response."""


@dataclass(
    frozen=True,
    slots=True,
)
class OAuthTokenSet:
    access_token: str
    id_token: str
    token_type: str
    expires_in: int
    refresh_token: str | None
    refresh_expires_in: int | None
    scope: str | None


def _required_str(
    payload: dict[str, object],
    name: str,
) -> str:
    value = payload.get(name)

    if not isinstance(value, str) or not value:
        raise InvalidTokenResponseError(f"Token response is missing {name}.")

    return value


def _required_int(
    payload: dict[str, object],
    name: str,
) -> int:
    value = payload.get(name)

    if not isinstance(value, int) or isinstance(value, bool):
        raise InvalidTokenResponseError(f"Token response is missing {name}.")

    return value


def _optional_str(
    payload: dict[str, object],
    name: str,
) -> str | None:
    value = payload.get(name)

    if value is None:
        return None

    if not isinstance(value, str):
        raise InvalidTokenResponseError(f"Token response contains invalid {name}.")

    return value


def _optional_int(
    payload: dict[str, object],
    name: str,
) -> int | None:
    value = payload.get(name)

    if value is None:
        return None

    if not isinstance(value, int) or isinstance(value, bool):
        raise InvalidTokenResponseError(f"Token response contains invalid {name}.")

    return value


def _parse_token_response(
    response: httpx.Response,
) -> OAuthTokenSet:
    raw_payload: object = response.json()

    if not isinstance(raw_payload, dict):
        raise InvalidTokenResponseError("Token response is not a JSON object.")

    payload: dict[str, object] = {
        key: value for key, value in raw_payload.items() if isinstance(key, str)
    }

    return OAuthTokenSet(
        access_token=_required_str(
            payload,
            "access_token",
        ),
        id_token=_required_str(
            payload,
            "id_token",
        ),
        token_type=_required_str(
            payload,
            "token_type",
        ),
        expires_in=_required_int(
            payload,
            "expires_in",
        ),
        refresh_token=_optional_str(
            payload,
            "refresh_token",
        ),
        refresh_expires_in=_optional_int(
            payload,
            "refresh_expires_in",
        ),
        scope=_optional_str(
            payload,
            "scope",
        ),
    )


async def _exchange(
    *,
    client: httpx.AsyncClient,
    config: TokenExchangeConfig,
    code: str,
    code_verifier: str,
) -> OAuthTokenSet:
    realm = quote(
        config.keycloak_realm,
        safe="",
    )

    token_endpoint = f"{config.keycloak_internal_url}/realms/{realm}/protocol/openid-connect/token"

    try:
        response = await client.post(
            token_endpoint,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": config.redirect_uri,
                "code_verifier": code_verifier,
            },
            auth=httpx.BasicAuth(
                config.client_id,
                config.client_secret,
            ),
        )
    except httpx.HTTPError as exc:
        raise TokenExchangeUnavailableError("Identity provider is unavailable.") from exc

    if response.status_code >= 500:
        raise TokenExchangeUnavailableError("Identity provider returned a server error.")

    if response.status_code != 200:
        raise TokenExchangeRejectedError("Authorization-code exchange was rejected.")

    try:
        return _parse_token_response(response)
    except ValueError as exc:
        raise InvalidTokenResponseError("Token response is not valid JSON.") from exc


async def exchange_authorization_code(
    *,
    config: TokenExchangeConfig,
    code: str,
    code_verifier: str,
    client: httpx.AsyncClient | None = None,
) -> OAuthTokenSet:
    if client is not None:
        return await _exchange(
            client=client,
            config=config,
            code=code,
            code_verifier=code_verifier,
        )

    async with httpx.AsyncClient(
        timeout=config.timeout_seconds,
    ) as owned_client:
        return await _exchange(
            client=owned_client,
            config=config,
            code=code,
            code_verifier=code_verifier,
        )
