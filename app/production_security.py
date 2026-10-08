from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlparse


class ProductionSecurityError(RuntimeError):
    pass


@dataclass(
    frozen=True,
    slots=True,
)
class ProductionSecurityResult:
    production: bool
    tls_enforced: bool
    secure_cookies: bool
    keycloak_admin_separated: bool


def validate_production_security(
    environ: dict[str, str] | None = None,
) -> ProductionSecurityResult:
    env = os.environ if environ is None else environ

    app_env = (
        env.get(
            "APP_ENV",
            "development",
        )
        .strip()
        .lower()
    )

    production = app_env in {
        "production",
        "prod",
    }

    if not production:
        return ProductionSecurityResult(
            production=False,
            tls_enforced=False,
            secure_cookies=False,
            keycloak_admin_separated=False,
        )

    platform_url = _required(
        env,
        "PLATFORM_PUBLIC_URL",
    )

    keycloak_public_url = _required(
        env,
        "KEYCLOAK_PUBLIC_URL",
    )

    keycloak_admin_url = _required(
        env,
        "KC_HOSTNAME_ADMIN",
    )

    redirect_uri = _required(
        env,
        "AUTH_REDIRECT_URI",
    )

    platform = _require_https_url(
        "PLATFORM_PUBLIC_URL",
        platform_url,
    )

    keycloak_public = _require_https_url(
        "KEYCLOAK_PUBLIC_URL",
        keycloak_public_url,
    )

    keycloak_admin = _require_https_url(
        "KC_HOSTNAME_ADMIN",
        keycloak_admin_url,
    )

    redirect = _require_https_url(
        "AUTH_REDIRECT_URI",
        redirect_uri,
    )

    if platform.hostname != redirect.hostname:
        raise ProductionSecurityError("AUTH_REDIRECT_URI must use the platform public hostname.")

    if keycloak_public.hostname == keycloak_admin.hostname:
        raise ProductionSecurityError("Keycloak administration must use a separate hostname.")

    if not _required_true(
        env,
        "AUTH_SESSION_COOKIE_SECURE",
    ):
        raise ProductionSecurityError("AUTH_SESSION_COOKIE_SECURE must be true in production.")

    if not _required_true(
        env,
        "AUTH_TRANSACTION_COOKIE_SECURE",
    ):
        raise ProductionSecurityError("AUTH_TRANSACTION_COOKIE_SECURE must be true in production.")

    if (
        _optional_bool(
            env,
            "KC_HOSTNAME_STRICT",
            default=True,
        )
        is False
    ):
        raise ProductionSecurityError("KC_HOSTNAME_STRICT must not be disabled in production.")

    if _optional_bool(
        env,
        "KC_HOSTNAME_DEBUG",
        default=False,
    ):
        raise ProductionSecurityError("KC_HOSTNAME_DEBUG must be disabled in production.")

    return ProductionSecurityResult(
        production=True,
        tls_enforced=True,
        secure_cookies=True,
        keycloak_admin_separated=True,
    )


def _required(
    environ: dict[str, str],
    name: str,
) -> str:
    value = environ.get(name)

    if value is None or not value.strip():
        raise ProductionSecurityError(f"{name} is required in production.")

    return value.strip()


def _require_https_url(
    name: str,
    value: str,
):
    parsed = urlparse(value)

    if (
        parsed.scheme != "https"
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ProductionSecurityError(f"{name} must be a valid HTTPS URL in production.")

    return parsed


def _required_true(
    environ: dict[str, str],
    name: str,
) -> bool:
    value = _required(
        environ,
        name,
    )

    return _parse_bool(
        name,
        value,
    )


def _optional_bool(
    environ: dict[str, str],
    name: str,
    *,
    default: bool,
) -> bool:
    value = environ.get(name)

    if value is None:
        return default

    return _parse_bool(
        name,
        value,
    )


def _parse_bool(
    name: str,
    value: str,
) -> bool:
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

    raise ProductionSecurityError(f"{name} contains an invalid boolean value.")


def main() -> None:
    result = validate_production_security()

    if not result.production:
        print("Production security check skipped: APP_ENV is not production.")
        return

    print("PASS: production TLS configuration")
    print("PASS: secure cookies")
    print("PASS: separate Keycloak admin hostname")
    print("PASS: strict Keycloak hostname configuration")


if __name__ == "__main__":
    main()
