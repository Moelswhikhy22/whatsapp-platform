from __future__ import annotations

from typing import Annotated
from unittest.mock import (
    AsyncMock,
    MagicMock,
    patch,
)

from fastapi import (
    Depends,
    FastAPI,
)
from fastapi.testclient import TestClient

from app.api.dependencies.human_auth import (
    require_human_principal,
)
from app.api.dependencies.service_auth import (
    require_service_principal,
)
from app.auth.id_token import (
    HumanPrincipal,
)
from app.auth.service_token import (
    InvalidServiceTokenError,
    ServicePrincipal,
)
from app.auth.session_cookie import (
    SESSION_COOKIE_NAME,
)
from app.auth.session_store import (
    SessionRecord,
)
from app.db.models.security_access_log import (
    SecurityAccessOutcome,
    SecurityPrincipalType,
)


def _session() -> str:
    return SessionRecord(
        status="authenticated",
        access_token="access-token",
        id_token="id-token",
        refresh_token="refresh-token",
        token_type="Bearer",
        expires_in=300,
        refresh_expires_in=1800,
        scope="openid profile email",
        nonce="nonce",
        subject="keycloak-user-123",
    ).to_json()


def _human_client() -> tuple[
    TestClient,
    AsyncMock,
]:
    application = FastAPI()

    redis = AsyncMock()

    application.state.redis = redis

    @application.get("/protected")
    async def protected(
        principal: Annotated[
            HumanPrincipal,
            Depends(require_human_principal),
        ],
    ) -> dict[str, str]:
        return {"subject": principal.subject}

    return (
        TestClient(application),
        redis,
    )


def _service_client() -> TestClient:
    application = FastAPI()

    @application.get("/service-protected")
    async def protected(
        principal: Annotated[
            ServicePrincipal,
            Depends(require_service_principal),
        ],
    ) -> dict[str, str]:
        return {"client_id": (principal.client_id)}

    return TestClient(application)


def test_human_auth_success_writes_security_event() -> None:
    client, redis = _human_client()

    redis.get.return_value = _session()

    client.cookies.set(
        SESSION_COOKIE_NAME,
        "test-session",
    )

    security_writer = AsyncMock()

    with patch(
        ("app.api.dependencies.human_auth.record_security_access"),
        security_writer,
    ):
        response = client.get("/protected")

    assert response.status_code == 200

    security_writer.assert_awaited_once()

    call = security_writer.await_args

    assert call.kwargs["principal_type"] is SecurityPrincipalType.HUMAN

    assert call.kwargs["principal_id"] == "keycloak-user-123"

    assert call.kwargs["event"] == "human.session_authentication"

    assert call.kwargs["outcome"] is SecurityAccessOutcome.SUCCESS


def test_missing_session_cookie_writes_denied_event() -> None:
    client, _redis = _human_client()

    security_writer = AsyncMock()

    with patch(
        ("app.api.dependencies.human_auth.record_security_access"),
        security_writer,
    ):
        response = client.get("/protected")

    assert response.status_code == 401

    call = security_writer.await_args

    assert call.kwargs["principal_type"] is SecurityPrincipalType.ANONYMOUS

    assert call.kwargs["principal_id"] is None

    assert call.kwargs["outcome"] is SecurityAccessOutcome.DENIED

    assert call.kwargs["reason_code"] == "missing_session_cookie"


def test_service_auth_success_writes_security_event() -> None:
    client = _service_client()

    validator = MagicMock()

    validator.validate = AsyncMock(
        return_value=ServicePrincipal(
            client_id="odoo-service",
            subject="service-subject",
            scopes=frozenset({("whatsapp-platform-api-access")}),
        )
    )

    security_writer = AsyncMock()

    with (
        patch(
            ("app.api.dependencies.service_auth.get_service_token_validator"),
            return_value=validator,
        ),
        patch(
            ("app.api.dependencies.service_auth.record_security_access"),
            security_writer,
        ),
    ):
        response = client.get(
            "/service-protected",
            headers={"Authorization": ("Bearer trusted-token")},
        )

    assert response.status_code == 200

    call = security_writer.await_args

    assert call.kwargs["principal_type"] is SecurityPrincipalType.INTEGRATION

    assert call.kwargs["principal_id"] == "odoo-service"

    assert call.kwargs["event"] == "service.token_authentication"

    assert call.kwargs["outcome"] is SecurityAccessOutcome.SUCCESS

    serialized = str(call.kwargs)

    assert "trusted-token" not in serialized


def test_invalid_service_token_writes_denied_event() -> None:
    client = _service_client()

    validator = MagicMock()

    validator.validate = AsyncMock(side_effect=(InvalidServiceTokenError("Invalid token.")))

    security_writer = AsyncMock()

    with (
        patch(
            ("app.api.dependencies.service_auth.get_service_token_validator"),
            return_value=validator,
        ),
        patch(
            ("app.api.dependencies.service_auth.record_security_access"),
            security_writer,
        ),
    ):
        response = client.get(
            "/service-protected",
            headers={"Authorization": ("Bearer secret-token")},
        )

    assert response.status_code == 401

    call = security_writer.await_args

    assert call.kwargs["principal_type"] is SecurityPrincipalType.ANONYMOUS

    assert call.kwargs["principal_id"] is None

    assert call.kwargs["outcome"] is SecurityAccessOutcome.DENIED

    assert call.kwargs["reason_code"] == "invalid_bearer_token"

    serialized = str(call.kwargs)

    assert "secret-token" not in serialized
