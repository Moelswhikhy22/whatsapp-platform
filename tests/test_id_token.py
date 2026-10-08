from __future__ import annotations

import time
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.auth.id_token import (
    IdTokenConfig,
    IdTokenValidator,
    InvalidIdTokenError,
)


class StaticSigningKeyProvider:
    def __init__(
        self,
        public_key: rsa.RSAPublicKey,
    ) -> None:
        self._public_key = public_key

    async def get_signing_key(
        self,
        kid: str,
    ) -> rsa.RSAPublicKey:
        assert kid == "test-key"

        return self._public_key


def create_validator_and_private_key() -> tuple[
    IdTokenValidator,
    rsa.RSAPrivateKey,
]:
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    config = IdTokenConfig(
        issuer="https://keycloak.example/realms/test",
        jwks_url="http://keycloak/realms/test/certs",
        client_id="whatsapp-platform-bff",
        jwks_cache_ttl_seconds=300,
        http_timeout_seconds=5.0,
    )

    validator = IdTokenValidator(
        config=config,
        key_provider=StaticSigningKeyProvider(
            private_key.public_key(),
        ),
    )

    return validator, private_key


def create_token(
    *,
    private_key: rsa.RSAPrivateKey,
    nonce: str = "expected-nonce",
    audience: str = "whatsapp-platform-bff",
    issuer: str = ("https://keycloak.example/realms/test"),
    subject: str = "keycloak-user-123",
) -> str:
    now = int(time.time())

    return jwt.encode(
        {
            "iss": issuer,
            "aud": audience,
            "azp": audience,
            "sub": subject,
            "nonce": nonce,
            "iat": now,
            "exp": now + 300,
            "jti": str(uuid4()),
        },
        private_key,
        algorithm="RS256",
        headers={
            "kid": "test-key",
        },
    )


@pytest.mark.asyncio
async def test_valid_id_token_returns_human_principal() -> None:
    validator, private_key = create_validator_and_private_key()

    token = create_token(
        private_key=private_key,
    )

    principal = await validator.validate(
        token=token,
        expected_nonce="expected-nonce",
    )

    assert principal.subject == "keycloak-user-123"


@pytest.mark.asyncio
async def test_id_token_rejects_wrong_nonce() -> None:
    validator, private_key = create_validator_and_private_key()

    token = create_token(
        private_key=private_key,
        nonce="wrong-nonce",
    )

    with pytest.raises(
        InvalidIdTokenError,
        match="nonce does not match",
    ):
        await validator.validate(
            token=token,
            expected_nonce="expected-nonce",
        )


@pytest.mark.asyncio
async def test_id_token_rejects_wrong_audience() -> None:
    validator, private_key = create_validator_and_private_key()

    token = create_token(
        private_key=private_key,
        audience="another-client",
    )

    with pytest.raises(
        InvalidIdTokenError,
        match="Invalid ID token",
    ):
        await validator.validate(
            token=token,
            expected_nonce="expected-nonce",
        )


@pytest.mark.asyncio
async def test_id_token_rejects_wrong_issuer() -> None:
    validator, private_key = create_validator_and_private_key()

    token = create_token(
        private_key=private_key,
        issuer="https://attacker.example/realms/test",
    )

    with pytest.raises(
        InvalidIdTokenError,
        match="Invalid ID token",
    ):
        await validator.validate(
            token=token,
            expected_nonce="expected-nonce",
        )
