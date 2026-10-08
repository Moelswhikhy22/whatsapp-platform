from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlparse


class AuthConfigurationError(RuntimeError):
    """Raised when required authentication configuration is missing."""


def _required_env(
    name: str,
) -> str:
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


def _is_production() -> bool:
    return os.getenv(
        "APP_ENV",
        "development",
    ).strip().lower() in {
        "production",
        "prod",
    }


def _require_https_in_production(
    *,
    name: str,
    value: str,
) -> None:
    if not _is_production():
        return

    parsed = urlparse(value)

    if parsed.scheme != "https" or parsed.hostname is None:
        raise AuthConfigurationError(f"{name} must use HTTPS in production.")


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
    production = _is_production()

    keycloak_public_url = _required_env("KEYCLOAK_PUBLIC_URL").rstrip("/")

    redirect_uri = _required_env("AUTH_REDIRECT_URI")

    transaction_cookie_secure = _env_bool(
        "AUTH_TRANSACTION_COOKIE_SECURE",
        default=production,
    )

    _require_https_in_production(
        name="KEYCLOAK_PUBLIC_URL",
        value=keycloak_public_url,
    )

    _require_https_in_production(
        name="AUTH_REDIRECT_URI",
        value=redirect_uri,
    )

    if production and not transaction_cookie_secure:
        raise AuthConfigurationError(
            "Authentication transaction cookies must be Secure in production."
        )

    return AuthLoginConfig(
        keycloak_public_url=(keycloak_public_url),
        keycloak_realm=_required_env("KEYCLOAK_REALM"),
        client_id=_required_env("KEYCLOAK_BFF_CLIENT_ID"),
        redirect_uri=redirect_uri,
        transaction_cookie_secure=(transaction_cookie_secure),
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
        keycloak_internal_url=(_required_env("KEYCLOAK_INTERNAL_URL").rstrip("/")),
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
    production = _is_production()

    secure = _env_bool(
        "AUTH_SESSION_COOKIE_SECURE",
        default=production,
    )

    if production and not secure:
        raise AuthConfigurationError("Session cookies must be Secure in production.")

    return SessionCookieConfig(
        secure=secure,
        max_age_seconds=28_800,
    )
