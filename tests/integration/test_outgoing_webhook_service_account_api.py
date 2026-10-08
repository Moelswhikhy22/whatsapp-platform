from __future__ import annotations

import os
from dataclasses import dataclass
from uuid import UUID, uuid4

import httpx
import jwt
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.api.v1.outgoing_webhooks import (
    router as outgoing_webhooks_router,
)
from app.auth.service_token import (
    get_service_token_validator,
)
from app.db.models.integration import (
    Integration,
    IntegrationProvider,
)
from app.db.models.outgoing_webhook import (
    OutgoingWebhookDelivery,
    OutgoingWebhookSubscription,
)
from app.db.models.tenant import (
    Tenant,
    TenantStatus,
)


EXPECTED_AUDIENCE = "whatsapp-platform-api"

EXPECTED_BASE_SCOPE = "whatsapp-platform-api-access"

EXPECTED_WEBHOOK_SCOPE = "webhook:manage"


@dataclass(
    frozen=True,
    slots=True,
)
class WebhookServiceAccountEnvironment:
    app: FastAPI
    client_id: str
    tenant_a_id: UUID
    tenant_b_id: UUID
    tenant_a_subscription_id: UUID
    tenant_b_subscription_id: UUID
    tenant_b_delivery_id: UUID


def _required_test_env(
    name: str,
) -> str:
    value = os.getenv(name)

    if value is None or not value.strip():
        pytest.skip(f"{name} is not configured.")

    return value.strip()


async def _get_real_service_token(
    *,
    client_id: str,
) -> str:
    public_url = _required_test_env("KEYCLOAK_PUBLIC_URL").rstrip("/")

    realm = _required_test_env("KEYCLOAK_REALM")

    client_secret = _required_test_env("KEYCLOAK_TEST_CLIENT_SECRET")

    token_url = f"{public_url}/realms/{realm}/protocol/openid-connect/token"

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            token_url,
            data={
                "grant_type": ("client_credentials"),
                "client_id": client_id,
                "client_secret": (client_secret),
            },
        )

    assert response.status_code == 200, (
        f"Keycloak Client Credentials request failed: {response.status_code} {response.text}"
    )

    payload = response.json()

    access_token = payload.get("access_token")

    assert isinstance(
        access_token,
        str,
    )

    assert access_token

    return access_token


def _assert_keycloak_token_contract(
    *,
    token: str,
    expected_client_id: str,
) -> None:
    claims = jwt.decode(
        token,
        options={
            "verify_signature": False,
            "verify_aud": False,
            "verify_exp": False,
        },
    )

    assert claims.get("azp") == expected_client_id, (
        "Keycloak token does not contain the expected azp/client identity."
    )

    raw_audience = claims.get("aud")

    if isinstance(
        raw_audience,
        str,
    ):
        audiences = {raw_audience}

    elif isinstance(
        raw_audience,
        list,
    ):
        audiences = {
            item
            for item in raw_audience
            if isinstance(
                item,
                str,
            )
        }

    else:
        audiences = set()

    assert EXPECTED_AUDIENCE in audiences, (
        f"Keycloak test client token is missing audience {EXPECTED_AUDIENCE!r}."
    )

    raw_scope = claims.get(
        "scope",
        "",
    )

    assert isinstance(
        raw_scope,
        str,
    )

    scopes = {item for item in raw_scope.split() if item}

    assert EXPECTED_BASE_SCOPE in scopes, (
        f"Keycloak test client token is missing base API scope {EXPECTED_BASE_SCOPE!r}."
    )

    assert EXPECTED_WEBHOOK_SCOPE in scopes, (
        f"Keycloak test client token is missing webhook scope {EXPECTED_WEBHOOK_SCOPE!r}."
    )


async def _seed_environment(
    *,
    session_factory: (async_sessionmaker[AsyncSession]),
    client_id: str,
) -> WebhookServiceAccountEnvironment:
    tenant_a_id = uuid4()
    tenant_b_id = uuid4()

    tenant_a_subscription_id = uuid4()

    tenant_b_subscription_id = uuid4()

    tenant_b_delivery_id = uuid4()

    tenant_a = Tenant(
        id=tenant_a_id,
        name="Webhook Tenant A",
        slug=(f"webhook-a-{tenant_a_id.hex[:12]}"),
        status=TenantStatus.ACTIVE,
    )

    tenant_b = Tenant(
        id=tenant_b_id,
        name="Webhook Tenant B",
        slug=(f"webhook-b-{tenant_b_id.hex[:12]}"),
        status=TenantStatus.ACTIVE,
    )

    integration_a = Integration(
        id=uuid4(),
        tenant_id=tenant_a_id,
        provider=(IntegrationProvider.ODOO),
        name="Webhook Service Account",
        external_account_id=None,
        keycloak_client_id=(client_id),
        config_json={},
        active=True,
    )

    subscription_a = OutgoingWebhookSubscription(
        id=(tenant_a_subscription_id),
        tenant_id=tenant_a_id,
        name="Tenant A webhook",
        endpoint_url=("https://tenant-a.example.test/webhook"),
        event_types_json=["message.received"],
        vault_secret_reference=(
            f"whatsapp-platform/tenants/{tenant_a_id}/webhooks/test/signing/test"
        ),
        active=True,
    )

    subscription_b = OutgoingWebhookSubscription(
        id=(tenant_b_subscription_id),
        tenant_id=tenant_b_id,
        name="Tenant B webhook",
        endpoint_url=("https://tenant-b.example.test/webhook"),
        event_types_json=["message.received"],
        vault_secret_reference=(
            f"whatsapp-platform/tenants/{tenant_b_id}/webhooks/test/signing/test"
        ),
        active=True,
    )

    delivery_b = OutgoingWebhookDelivery(
        id=tenant_b_delivery_id,
        tenant_id=tenant_b_id,
        subscription_id=(tenant_b_subscription_id),
        event_id=uuid4(),
        event_type=("message.received"),
        payload_json={
            "id": str(uuid4()),
            "type": ("message.received"),
            "data": {},
        },
    )

    async with session_factory() as session:
        session.add_all(
            [
                tenant_a,
                tenant_b,
            ]
        )

        await session.flush()

        session.add(integration_a)

        session.add_all(
            [
                subscription_a,
                subscription_b,
            ]
        )

        await session.flush()

        session.add(delivery_b)

        await session.flush()

    app = FastAPI()

    app.state.session_factory = session_factory

    app.include_router(
        outgoing_webhooks_router,
        prefix="/api/v1",
    )

    return WebhookServiceAccountEnvironment(
        app=app,
        client_id=client_id,
        tenant_a_id=tenant_a_id,
        tenant_b_id=tenant_b_id,
        tenant_a_subscription_id=(tenant_a_subscription_id),
        tenant_b_subscription_id=(tenant_b_subscription_id),
        tenant_b_delivery_id=(tenant_b_delivery_id),
    )


async def _create_database_environment() -> tuple[
    AsyncEngine,
    AsyncConnection,
    object,
    WebhookServiceAccountEnvironment,
]:
    database_url = _required_test_env("TEST_DATABASE_URL")

    client_id = _required_test_env("KEYCLOAK_TEST_CLIENT_ID")

    engine = create_async_engine(
        database_url,
        pool_pre_ping=True,
    )

    connection = await engine.connect()

    transaction = await connection.begin()

    session_factory = async_sessionmaker(
        bind=connection,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    environment = await _seed_environment(
        session_factory=(session_factory),
        client_id=client_id,
    )

    return (
        engine,
        connection,
        transaction,
        environment,
    )


async def _close_database_environment(
    *,
    engine: AsyncEngine,
    connection: AsyncConnection,
    transaction: object,
) -> None:
    rollback = getattr(
        transaction,
        "rollback",
    )

    await rollback()

    await connection.close()

    await engine.dispose()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_keycloak_service_account_lists_only_own_tenant_webhooks() -> None:
    (
        engine,
        connection,
        transaction,
        environment,
    ) = await _create_database_environment()

    try:
        token = await _get_real_service_token(client_id=(environment.client_id))

        _assert_keycloak_token_contract(
            token=token,
            expected_client_id=(environment.client_id),
        )

        # Ensure this test uses the current
        # real environment instead of any
        # validator cached by another test.
        get_service_token_validator.cache_clear()

        transport = httpx.ASGITransport(app=environment.app)

        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            response = await client.get(
                "/api/v1/webhooks",
                headers={"Authorization": (f"Bearer {token}")},
            )

        assert response.status_code == 200, response.text

        payload = response.json()

        returned_ids = {item["id"] for item in payload}

        assert str(environment.tenant_a_subscription_id) in returned_ids

        assert str(environment.tenant_b_subscription_id) not in returned_ids

    finally:
        get_service_token_validator.cache_clear()

        await _close_database_environment(
            engine=engine,
            connection=connection,
            transaction=transaction,
        )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_keycloak_service_account_cannot_read_other_tenant_delivery() -> None:
    (
        engine,
        connection,
        transaction,
        environment,
    ) = await _create_database_environment()

    try:
        token = await _get_real_service_token(client_id=(environment.client_id))

        _assert_keycloak_token_contract(
            token=token,
            expected_client_id=(environment.client_id),
        )

        get_service_token_validator.cache_clear()

        transport = httpx.ASGITransport(app=environment.app)

        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            response = await client.get(
                (f"/api/v1/webhooks/deliveries/{environment.tenant_b_delivery_id}/attempts"),
                headers={"Authorization": (f"Bearer {token}")},
            )

        # Cross-tenant existence must not leak.
        assert response.status_code == 404

        payload = response.json()

        assert payload["detail"]["code"] == ("WEBHOOK_DELIVERY_NOT_FOUND")

    finally:
        get_service_token_validator.cache_clear()

        await _close_database_environment(
            engine=engine,
            connection=connection,
            transaction=transaction,
        )
