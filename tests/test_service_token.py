from __future__ import annotations

from datetime import (
    UTC,
    datetime,
    timedelta,
)

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import (
    rsa,
)
from cryptography.hazmat.primitives.asymmetric.rsa import (
    RSAPrivateKey,
    RSAPublicKey,
)
from pytest import MonkeyPatch

from app.auth.service_token import (
    InvalidServiceTokenError,
    MissingRequiredScopeError,
    ServiceTokenConfig,
    ServiceTokenValidator,
    load_service_token_config,
)


class StaticKeyProvider:
    def __init__(
        self,
        *,
        public_key: RSAPublicKey,
        kid: str = "test-key",
    ) -> None:
        self._public_key = public_key
        self._kid = kid

    async def get_signing_key(
        self,
        kid: str,
    ) -> RSAPublicKey:
        if kid != self._kid:
            raise InvalidServiceTokenError("Unknown signing key.")

        return self._public_key


def _private_key() -> RSAPrivateKey:
    return rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )


def _config() -> ServiceTokenConfig:
    return ServiceTokenConfig(
        issuer=("http://localhost:8081/realms/whatsapp-platform"),
        jwks_url=("http://keycloak:8080/realms/whatsapp-platform/protocol/openid-connect/certs"),
        audience=("whatsapp-platform-api"),
        required_scope=("whatsapp-platform-api-access"),
        jwks_cache_ttl_seconds=300,
        http_timeout_seconds=5.0,
    )


def _validator(
    private_key: RSAPrivateKey,
) -> ServiceTokenValidator:
    public_key = private_key.public_key()

    provider = StaticKeyProvider(public_key=public_key)

    return ServiceTokenValidator(
        config=_config(),
        key_provider=provider,
    )


def _token(
    private_key: RSAPrivateKey,
    *,
    issuer: str | None = None,
    audience: object | None = None,
    scope: str | None = None,
    expires_at: datetime | None = None,
    client_id: str | None = ("whatsapp-platform-odoo-dev"),
    kid: str = "test-key",
) -> str:
    now = datetime.now(UTC)

    payload: dict[str, object] = {
        "iss": (issuer or _config().issuer),
        "aud": (
            audience
            if audience is not None
            else [
                "whatsapp-platform-api",
                "account",
            ]
        ),
        "sub": "service-account-subject",
        "exp": (expires_at or now + timedelta(minutes=5)),
        "iat": now,
        "scope": (scope if scope is not None else ("whatsapp-platform-api-access profile email")),
    }

    if client_id is not None:
        payload["azp"] = client_id

    return jwt.encode(
        payload,
        private_key,
        algorithm="RS256",
        headers={
            "kid": kid,
        },
    )


def test_load_service_token_config(
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

    config = load_service_token_config()

    assert config.issuer == ("http://localhost:8081/realms/whatsapp-platform")

    assert config.jwks_url == (
        "http://keycloak:8080/realms/whatsapp-platform/protocol/openid-connect/certs"
    )

    assert config.audience == ("whatsapp-platform-api")

    assert config.required_scope == ("whatsapp-platform-api-access")


@pytest.mark.asyncio
async def test_valid_service_token_is_accepted() -> None:
    private_key = _private_key()

    principal = await _validator(private_key).validate(_token(private_key))

    assert principal.client_id == ("whatsapp-platform-odoo-dev")

    assert principal.subject == ("service-account-subject")

    assert "whatsapp-platform-api-access" in principal.scopes


@pytest.mark.asyncio
async def test_invalid_signature_is_rejected() -> None:
    trusted_key = _private_key()
    attacker_key = _private_key()

    validator = _validator(trusted_key)

    with pytest.raises(InvalidServiceTokenError):
        await validator.validate(_token(attacker_key))


@pytest.mark.asyncio
async def test_wrong_issuer_is_rejected() -> None:
    private_key = _private_key()

    validator = _validator(private_key)

    with pytest.raises(InvalidServiceTokenError):
        await validator.validate(
            _token(
                private_key,
                issuer=("https://attacker.example/realms/fake"),
            )
        )


@pytest.mark.asyncio
async def test_wrong_audience_is_rejected() -> None:
    private_key = _private_key()

    validator = _validator(private_key)

    with pytest.raises(InvalidServiceTokenError):
        await validator.validate(
            _token(
                private_key,
                audience=["another-api"],
            )
        )


@pytest.mark.asyncio
async def test_expired_token_is_rejected() -> None:
    private_key = _private_key()

    validator = _validator(private_key)

    with pytest.raises(InvalidServiceTokenError):
        await validator.validate(
            _token(
                private_key,
                expires_at=(datetime.now(UTC) - timedelta(seconds=1)),
            )
        )


@pytest.mark.asyncio
async def test_missing_required_scope_is_rejected() -> None:
    private_key = _private_key()

    validator = _validator(private_key)

    with pytest.raises(MissingRequiredScopeError):
        await validator.validate(
            _token(
                private_key,
                scope="profile email",
            )
        )


@pytest.mark.asyncio
async def test_missing_client_identity_is_rejected() -> None:
    private_key = _private_key()

    validator = _validator(private_key)

    with pytest.raises(InvalidServiceTokenError):
        await validator.validate(
            _token(
                private_key,
                client_id=None,
            )
        )


@pytest.mark.asyncio
async def test_malformed_token_is_rejected() -> None:
    private_key = _private_key()

    validator = _validator(private_key)

    with pytest.raises(InvalidServiceTokenError):
        await validator.validate("not-a-jwt")
