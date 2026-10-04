from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from jwt.algorithms import RSAAlgorithm
from jwt.exceptions import InvalidKeyError, InvalidTokenError

from app.auth.config import AuthConfigurationError

_SIGNING_ALGORITHM = "RS256"
_DEFAULT_AUDIENCE = "whatsapp-platform-api"
_DEFAULT_REQUIRED_SCOPE = "whatsapp-platform-api-access"


class ServiceTokenError(RuntimeError):
    """Base error for service-token authentication."""


class InvalidServiceTokenError(ServiceTokenError):
    """Raised when a service token cannot be trusted."""


class MissingRequiredScopeError(ServiceTokenError):
    """Raised when a valid token lacks the required API scope."""

    def __init__(
        self,
        required_scope: str,
    ) -> None:
        self.required_scope = required_scope

        super().__init__(f"Required scope is missing: {required_scope}")


class JwksUnavailableError(ServiceTokenError):
    """Raised when Keycloak signing keys cannot be obtained."""


@dataclass(
    frozen=True,
    slots=True,
)
class ServiceTokenConfig:
    issuer: str
    jwks_url: str
    audience: str
    required_scope: str
    jwks_cache_ttl_seconds: int
    http_timeout_seconds: float


@dataclass(
    frozen=True,
    slots=True,
)
class ServicePrincipal:
    client_id: str
    subject: str
    scopes: frozenset[str]


class SigningKeyProvider(Protocol):
    async def get_signing_key(
        self,
        kid: str,
    ) -> RSAPublicKey:
        """Return the RSA public key for a JWT key ID."""


def _required_env(
    name: str,
) -> str:
    value = os.getenv(name)

    if value is None or not value.strip():
        raise AuthConfigurationError(f"Missing required environment variable: {name}")

    return value.strip()


def load_service_token_config() -> ServiceTokenConfig:
    public_url = _required_env("KEYCLOAK_PUBLIC_URL").rstrip("/")

    internal_url = _required_env("KEYCLOAK_INTERNAL_URL").rstrip("/")

    realm = _required_env("KEYCLOAK_REALM")

    audience = os.getenv(
        "KEYCLOAK_SERVICE_AUDIENCE",
        _DEFAULT_AUDIENCE,
    ).strip()

    required_scope = os.getenv(
        "KEYCLOAK_SERVICE_REQUIRED_SCOPE",
        _DEFAULT_REQUIRED_SCOPE,
    ).strip()

    if not audience:
        raise AuthConfigurationError("KEYCLOAK_SERVICE_AUDIENCE must not be empty.")

    if not required_scope:
        raise AuthConfigurationError("KEYCLOAK_SERVICE_REQUIRED_SCOPE must not be empty.")

    return ServiceTokenConfig(
        issuer=(f"{public_url}/realms/{realm}"),
        jwks_url=(f"{internal_url}/realms/{realm}/protocol/openid-connect/certs"),
        audience=audience,
        required_scope=required_scope,
        jwks_cache_ttl_seconds=300,
        http_timeout_seconds=5.0,
    )


class KeycloakJwksClient:
    def __init__(
        self,
        *,
        config: ServiceTokenConfig,
    ) -> None:
        self._config = config
        self._keys: dict[
            str,
            RSAPublicKey,
        ] = {}

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
                raise InvalidServiceTokenError("Unknown token signing key.")

            return signing_key

    async def _refresh(
        self,
    ) -> None:
        try:
            async with httpx.AsyncClient(
                timeout=(self._config.http_timeout_seconds),
            ) as client:
                response = await client.get(self._config.jwks_url)

                response.raise_for_status()

        except httpx.HTTPError as exc:
            raise JwksUnavailableError("Keycloak signing keys are unavailable.") from exc

        try:
            payload: object = response.json()
        except ValueError as exc:
            raise JwksUnavailableError("Keycloak returned invalid JWKS data.") from exc

        if not isinstance(
            payload,
            dict,
        ):
            raise JwksUnavailableError("Keycloak returned invalid JWKS data.")

        raw_keys = payload.get("keys")

        if not isinstance(
            raw_keys,
            list,
        ):
            raise JwksUnavailableError("Keycloak JWKS contains no keys.")

        signing_keys: dict[
            str,
            RSAPublicKey,
        ] = {}

        for raw_key in raw_keys:
            if not isinstance(
                raw_key,
                dict,
            ):
                continue

            key_data: dict[
                str,
                object,
            ] = {key: value for key, value in raw_key.items() if isinstance(key, str)}

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
            raise JwksUnavailableError("Keycloak JWKS contains no usable RSA signing keys.")

        self._keys = signing_keys

        self._cache_expires_at = time.monotonic() + self._config.jwks_cache_ttl_seconds


class ServiceTokenValidator:
    def __init__(
        self,
        *,
        config: ServiceTokenConfig,
        key_provider: SigningKeyProvider,
    ) -> None:
        self._config = config
        self._key_provider = key_provider

    async def validate(
        self,
        token: str,
    ) -> ServicePrincipal:
        try:
            header = jwt.get_unverified_header(token)
        except InvalidTokenError as exc:
            raise InvalidServiceTokenError("Invalid access token.") from exc

        algorithm = header.get("alg")
        kid = header.get("kid")

        if algorithm != _SIGNING_ALGORITHM:
            raise InvalidServiceTokenError("Unsupported token signing algorithm.")

        if not isinstance(kid, str) or not kid:
            raise InvalidServiceTokenError("Token signing key ID is missing.")

        signing_key = await self._key_provider.get_signing_key(kid)

        try:
            decoded = jwt.decode(
                token,
                key=signing_key,
                algorithms=[_SIGNING_ALGORITHM],
                issuer=self._config.issuer,
                audience=(self._config.audience),
                options={
                    "require": [
                        "exp",
                        "iss",
                        "aud",
                    ]
                },
            )
        except InvalidTokenError as exc:
            raise InvalidServiceTokenError("Invalid access token.") from exc

        claims: dict[
            str,
            object,
        ] = {key: value for key, value in decoded.items() if isinstance(key, str)}

        client_id = claims.get("azp")
        subject = claims.get("sub")

        if not isinstance(client_id, str) or not client_id:
            raise InvalidServiceTokenError("Token client identity is missing.")

        if not isinstance(subject, str) or not subject:
            raise InvalidServiceTokenError("Token subject is missing.")

        scopes = _parse_scopes(claims.get("scope"))

        if self._config.required_scope not in scopes:
            raise MissingRequiredScopeError(self._config.required_scope)

        return ServicePrincipal(
            client_id=client_id,
            subject=subject,
            scopes=scopes,
        )


def _parse_scopes(
    value: object,
) -> frozenset[str]:
    if isinstance(value, str):
        return frozenset(scope for scope in value.split() if scope)

    if isinstance(value, list):
        return frozenset(scope for scope in value if isinstance(scope, str) and scope)

    return frozenset()


@lru_cache(maxsize=1)
def get_service_token_validator() -> ServiceTokenValidator:
    config = load_service_token_config()

    key_provider = KeycloakJwksClient(config=config)

    return ServiceTokenValidator(
        config=config,
        key_provider=key_provider,
    )
