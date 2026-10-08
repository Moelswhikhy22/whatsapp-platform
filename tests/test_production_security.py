from __future__ import annotations

import pytest

from app.production_security import (
    ProductionSecurityError,
    validate_production_security,
)


def _production_env() -> dict[str, str]:
    return {
        "APP_ENV": "production",
        "PLATFORM_PUBLIC_URL": ("https://whatsapp.example.com"),
        "KEYCLOAK_PUBLIC_URL": ("https://login.example.com"),
        "KC_HOSTNAME_ADMIN": ("https://identity-admin.example.com"),
        "AUTH_REDIRECT_URI": ("https://whatsapp.example.com/auth/callback"),
        "AUTH_SESSION_COOKIE_SECURE": ("true"),
        "AUTH_TRANSACTION_COOKIE_SECURE": ("true"),
        "KC_HOSTNAME_STRICT": "true",
        "KC_HOSTNAME_DEBUG": "false",
    }


def test_development_does_not_require_production_urls() -> None:
    result = validate_production_security(
        {
            "APP_ENV": "development",
        }
    )

    assert result.production is False


def test_valid_production_security_configuration() -> None:
    result = validate_production_security(_production_env())

    assert result.production is True
    assert result.tls_enforced is True
    assert result.secure_cookies is True
    assert result.keycloak_admin_separated is True


@pytest.mark.parametrize(
    "name",
    [
        "PLATFORM_PUBLIC_URL",
        "KEYCLOAK_PUBLIC_URL",
        "KC_HOSTNAME_ADMIN",
        "AUTH_REDIRECT_URI",
    ],
)
def test_production_requires_https(
    name: str,
) -> None:
    env = _production_env()

    env[name] = env[name].replace(
        "https://",
        "http://",
    )

    with pytest.raises(ProductionSecurityError):
        validate_production_security(env)


def test_keycloak_admin_must_use_separate_hostname() -> None:
    env = _production_env()

    env["KC_HOSTNAME_ADMIN"] = env["KEYCLOAK_PUBLIC_URL"]

    with pytest.raises(ProductionSecurityError):
        validate_production_security(env)


@pytest.mark.parametrize(
    "name",
    [
        "AUTH_SESSION_COOKIE_SECURE",
        "AUTH_TRANSACTION_COOKIE_SECURE",
    ],
)
def test_production_rejects_insecure_cookie_flags(
    name: str,
) -> None:
    env = _production_env()

    env[name] = "false"

    with pytest.raises(ProductionSecurityError):
        validate_production_security(env)


def test_production_rejects_disabled_keycloak_hostname_strict() -> None:
    env = _production_env()

    env["KC_HOSTNAME_STRICT"] = "false"

    with pytest.raises(ProductionSecurityError):
        validate_production_security(env)


def test_production_rejects_keycloak_hostname_debug() -> None:
    env = _production_env()

    env["KC_HOSTNAME_DEBUG"] = "true"

    with pytest.raises(ProductionSecurityError):
        validate_production_security(env)


def test_redirect_uri_must_use_platform_hostname() -> None:
    env = _production_env()

    env["AUTH_REDIRECT_URI"] = "https://attacker.example/auth/callback"

    with pytest.raises(ProductionSecurityError):
        validate_production_security(env)
