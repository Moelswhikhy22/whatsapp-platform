from __future__ import annotations

import pytest
from fastapi import HTTPException
from pytest import MonkeyPatch
from starlette.requests import Request

from app.api.dependencies import (
    service_auth,
)
from app.auth.service_token import (
    InvalidServiceTokenError,
    JwksUnavailableError,
    MissingRequiredScopeError,
    ServicePrincipal,
)


class SuccessfulValidator:
    async def validate(
        self,
        token: str,
    ) -> ServicePrincipal:
        assert token == "valid-token"

        return ServicePrincipal(
            client_id=("whatsapp-platform-odoo-dev"),
            subject=("service-account-subject"),
            scopes=frozenset({"whatsapp-platform-api-access"}),
        )


class InvalidValidator:
    async def validate(
        self,
        token: str,
    ) -> ServicePrincipal:
        del token

        raise InvalidServiceTokenError("Invalid token.")


class MissingScopeValidator:
    async def validate(
        self,
        token: str,
    ) -> ServicePrincipal:
        del token

        raise MissingRequiredScopeError("whatsapp-platform-api-access")


class UnavailableValidator:
    async def validate(
        self,
        token: str,
    ) -> ServicePrincipal:
        del token

        raise JwksUnavailableError("JWKS unavailable.")


def _request(
    authorization: str | None = None,
) -> Request:
    headers: list[tuple[bytes, bytes]] = []

    if authorization is not None:
        headers.append(
            (
                b"authorization",
                authorization.encode("ascii"),
            )
        )

    return Request(
        {
            "type": "http",
            "headers": headers,
        }
    )


@pytest.mark.asyncio
async def test_valid_bearer_token_returns_principal(
    monkeypatch: MonkeyPatch,
) -> None:
    validator = SuccessfulValidator()

    monkeypatch.setattr(
        service_auth,
        "get_service_token_validator",
        lambda: validator,
    )

    principal = await service_auth.require_service_principal(_request("Bearer valid-token"))

    assert principal.client_id == ("whatsapp-platform-odoo-dev")


@pytest.mark.asyncio
async def test_missing_authorization_header_returns_401() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await service_auth.require_service_principal(_request())

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_wrong_authorization_scheme_returns_401() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await service_auth.require_service_principal(_request("Basic something"))

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_invalid_token_returns_401(
    monkeypatch: MonkeyPatch,
) -> None:
    validator = InvalidValidator()

    monkeypatch.setattr(
        service_auth,
        "get_service_token_validator",
        lambda: validator,
    )

    with pytest.raises(HTTPException) as exc_info:
        await service_auth.require_service_principal(_request("Bearer invalid-token"))

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_missing_scope_returns_403(
    monkeypatch: MonkeyPatch,
) -> None:
    validator = MissingScopeValidator()

    monkeypatch.setattr(
        service_auth,
        "get_service_token_validator",
        lambda: validator,
    )

    with pytest.raises(HTTPException) as exc_info:
        await service_auth.require_service_principal(_request("Bearer valid-token"))

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_jwks_failure_returns_503(
    monkeypatch: MonkeyPatch,
) -> None:
    validator = UnavailableValidator()

    monkeypatch.setattr(
        service_auth,
        "get_service_token_validator",
        lambda: validator,
    )

    with pytest.raises(HTTPException) as exc_info:
        await service_auth.require_service_principal(_request("Bearer valid-token"))

    assert exc_info.value.status_code == 503
