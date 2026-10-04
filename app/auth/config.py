from __future__ import annotations

import os
from dataclasses import dataclass


class AuthConfigurationError(RuntimeError):
    """Raised when required authentication configuration is missing."""


def _required_env(name: str) -> str:
    value = os.getenv(name)

    if value is None or not value.strip():
        raise AuthConfigurationError(f"Missing required environment variable: {name}")

    return value.strip()


def _env_bool(
    name: str,
    *,
    default: bool,
) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    normalized = value.strip().lower()

    if normalized in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return True

    if normalized in {
        "0",
        "false",
        "no",
        "off",
    }:
        return False

    raise AuthConfigurationError(f"Invalid boolean value for {name}.")


@dataclass(
    frozen=True,
    slots=True,
)
class AuthLoginConfig:
    keycloak_public_url: str
    keycloak_realm: str
    client_id: str
    redirect_uri: str
    transaction_cookie_secure: bool
    transaction_ttl_seconds: int


def load_auth_login_config() -> AuthLoginConfig:
    return AuthLoginConfig(
        keycloak_public_url=_required_env("KEYCLOAK_PUBLIC_URL").rstrip("/"),
        keycloak_realm=_required_env("KEYCLOAK_REALM"),
        client_id=_required_env("KEYCLOAK_BFF_CLIENT_ID"),
        redirect_uri=_required_env("AUTH_REDIRECT_URI"),
        transaction_cookie_secure=_env_bool(
            "AUTH_TRANSACTION_COOKIE_SECURE",
            default=False,
        ),
        transaction_ttl_seconds=300,
    )


@dataclass(
    frozen=True,
    slots=True,
)
class TokenExchangeConfig:
    keycloak_internal_url: str
    keycloak_realm: str
    client_id: str
    client_secret: str
    redirect_uri: str
    timeout_seconds: float


def load_token_exchange_config() -> TokenExchangeConfig:
    return TokenExchangeConfig(
        keycloak_internal_url=_required_env("KEYCLOAK_INTERNAL_URL").rstrip("/"),
        keycloak_realm=_required_env("KEYCLOAK_REALM"),
        client_id=_required_env("KEYCLOAK_BFF_CLIENT_ID"),
        client_secret=_required_env("KEYCLOAK_BFF_CLIENT_SECRET"),
        redirect_uri=_required_env("AUTH_REDIRECT_URI"),
        timeout_seconds=10.0,
    )


@dataclass(
    frozen=True,
    slots=True,
)
class SessionCookieConfig:
    secure: bool
    max_age_seconds: int


def load_session_cookie_config() -> SessionCookieConfig:
    return SessionCookieConfig(
        secure=_env_bool(
            "AUTH_SESSION_COOKIE_SECURE",
            default=False,
        ),
        max_age_seconds=28_800,
    )
