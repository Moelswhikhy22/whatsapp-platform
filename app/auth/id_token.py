from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from functools import lru_cache
from secrets import compare_digest
from typing import Protocol

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from jwt.algorithms import RSAAlgorithm
from jwt.exceptions import InvalidKeyError, InvalidTokenError

from app.auth.config import AuthConfigurationError, load_auth_login_config

_SIGNING_ALGORITHM = "RS256"


class IdTokenError(RuntimeError):
    """Base error for human ID-token validation."""


class InvalidIdTokenError(IdTokenError):
    """Raised when an ID token cannot be trusted."""


class IdTokenJwksUnavailableError(IdTokenError):
    """Raised when Keycloak signing keys cannot be obtained."""


@dataclass(
    frozen=True,
    slots=True,
)
class IdTokenConfig:
    issuer: str
    jwks_url: str
    client_id: str
    jwks_cache_ttl_seconds: int
    http_timeout_seconds: float


@dataclass(
    frozen=True,
    slots=True,
)
class HumanPrincipal:
    subject: str


class IdTokenSigningKeyProvider(Protocol):
    async def get_signing_key(
        self,
        kid: str,
    ) -> RSAPublicKey:
        """Return the RSA signing key for a JWT key ID."""


def load_id_token_config() -> IdTokenConfig:
    login_config = load_auth_login_config()

    from os import getenv

    internal_url = getenv("KEYCLOAK_INTERNAL_URL")

    if internal_url is None or not internal_url.strip():
        raise AuthConfigurationError("Missing required environment variable: KEYCLOAK_INTERNAL_URL")

    realm = login_config.keycloak_realm

    return IdTokenConfig(
        issuer=(f"{login_config.keycloak_public_url}/realms/{realm}"),
        jwks_url=(
            f"{internal_url.strip().rstrip('/')}/realms/{realm}/protocol/openid-connect/certs"
        ),
        client_id=login_config.client_id,
        jwks_cache_ttl_seconds=300,
        http_timeout_seconds=5.0,
    )


class KeycloakIdTokenJwksClient:
    def __init__(
        self,
        *,
        config: IdTokenConfig,
    ) -> None:
        self._config = config

        self._keys: dict[str, RSAPublicKey] = {}

        self._cache_expires_at = 0.0
        self._lock = asyncio.Lock()

    async def get_signing_key(
        self,
        kid: str,
    ) -> RSAPublicKey:
        now = time.monotonic()

        cached_key = self._keys.get(kid)

        if cached_key is not None and now < self._cache_expires_at:
            return cached_key

        async with self._lock:
            now = time.monotonic()

            cached_key = self._keys.get(kid)

            if cached_key is not None and now < self._cache_expires_at:
                return cached_key

            await self._refresh()

            signing_key = self._keys.get(kid)

            if signing_key is None:
                raise InvalidIdTokenError("Unknown ID-token signing key.")

            return signing_key

    async def _refresh(self) -> None:
        try:
            async with httpx.AsyncClient(
                timeout=self._config.http_timeout_seconds,
            ) as client:
                response = await client.get(self._config.jwks_url)

                response.raise_for_status()

        except httpx.HTTPError as exc:
            raise IdTokenJwksUnavailableError("Keycloak signing keys are unavailable.") from exc

        try:
            payload: object = response.json()
        except ValueError as exc:
            raise IdTokenJwksUnavailableError("Keycloak returned invalid JWKS data.") from exc

        if not isinstance(payload, dict):
            raise IdTokenJwksUnavailableError("Keycloak returned invalid JWKS data.")

        raw_keys = payload.get("keys")

        if not isinstance(raw_keys, list):
            raise IdTokenJwksUnavailableError("Keycloak JWKS contains no keys.")

        signing_keys: dict[str, RSAPublicKey] = {}

        for raw_key in raw_keys:
            if not isinstance(raw_key, dict):
                continue

            key_data: dict[str, object] = {
                key: value for key, value in raw_key.items() if isinstance(key, str)
            }

            kid = key_data.get("kid")
            key_type = key_data.get("kty")
            key_use = key_data.get("use")
            algorithm = key_data.get("alg")

            if not isinstance(kid, str) or not kid:
                continue

            if key_type != "RSA":
                continue

            if key_use not in {
                None,
                "sig",
            }:
                continue

            if algorithm not in {
                None,
                _SIGNING_ALGORITHM,
            }:
                continue

            try:
                parsed_key = RSAAlgorithm.from_jwk(key_data)
            except (
                InvalidKeyError,
                TypeError,
                ValueError,
            ):
                continue

            if not isinstance(
                parsed_key,
                RSAPublicKey,
            ):
                continue

            signing_keys[kid] = parsed_key

        if not signing_keys:
            raise IdTokenJwksUnavailableError("Keycloak JWKS contains no usable RSA signing keys.")

        self._keys = signing_keys

        self._cache_expires_at = time.monotonic() + self._config.jwks_cache_ttl_seconds


class IdTokenValidator:
    def __init__(
        self,
        *,
        config: IdTokenConfig,
        key_provider: IdTokenSigningKeyProvider,
    ) -> None:
        self._config = config
        self._key_provider = key_provider

    async def validate(
        self,
        *,
        token: str,
        expected_nonce: str,
    ) -> HumanPrincipal:
        try:
            header = jwt.get_unverified_header(token)
        except InvalidTokenError as exc:
            raise InvalidIdTokenError("Invalid ID token.") from exc

        algorithm = header.get("alg")
        kid = header.get("kid")

        if algorithm != _SIGNING_ALGORITHM:
            raise InvalidIdTokenError("Unsupported ID-token signing algorithm.")

        if not isinstance(kid, str) or not kid:
            raise InvalidIdTokenError("ID-token signing key ID is missing.")

        signing_key = await self._key_provider.get_signing_key(kid)

        try:
            decoded = jwt.decode(
                token,
                key=signing_key,
                algorithms=[_SIGNING_ALGORITHM],
                issuer=self._config.issuer,
                audience=self._config.client_id,
                options={
                    "require": [
                        "exp",
                        "iss",
                        "aud",
                        "sub",
                        "nonce",
                    ]
                },
            )

        except InvalidTokenError as exc:
            raise InvalidIdTokenError("Invalid ID token.") from exc

        claims: dict[str, object] = {
            key: value for key, value in decoded.items() if isinstance(key, str)
        }

        subject = claims.get("sub")
        nonce = claims.get("nonce")
        authorized_party = claims.get("azp")

        if not isinstance(subject, str) or not subject:
            raise InvalidIdTokenError("ID-token subject is missing.")

        if not isinstance(nonce, str):
            raise InvalidIdTokenError("ID-token nonce is missing.")

        if not compare_digest(
            nonce,
            expected_nonce,
        ):
            raise InvalidIdTokenError("ID-token nonce does not match.")

        if authorized_party is not None and authorized_party != self._config.client_id:
            raise InvalidIdTokenError("ID-token authorized party is invalid.")

        return HumanPrincipal(
            subject=subject,
        )


@lru_cache(maxsize=1)
def get_id_token_validator() -> IdTokenValidator:
    config = load_id_token_config()

    key_provider = KeycloakIdTokenJwksClient(
        config=config,
    )

    return IdTokenValidator(
        config=config,
        key_provider=key_provider,
    )
