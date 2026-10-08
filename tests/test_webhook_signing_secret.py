from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.db.models.outgoing_webhook import (
    OutgoingWebhookSubscription,
)
from app.integrations.vault.client import (
    VaultClient,
)
from app.integrations.webhooks.signing_secret import (
    VaultWebhookSigningSecretProvider,
    WebhookSigningSecretInvalidError,
)


@pytest.mark.asyncio
async def test_reads_webhook_signing_secret_from_tenant_namespace() -> None:
    tenant_id = uuid4()
    subscription_id = uuid4()

    reference = (
        f"whatsapp-platform/tenants/{tenant_id}/webhooks/{subscription_id}/signing/{uuid4()}"
    )

    subscription = OutgoingWebhookSubscription(
        id=subscription_id,
        tenant_id=tenant_id,
        name="ERP",
        endpoint_url=("https://example.com/hooks"),
        event_types_json=["message.received"],
        vault_secret_reference=(reference),
        active=True,
    )

    vault = AsyncMock(spec=VaultClient)

    vault.read_secret.return_value = {
        "signing_secret": "s" * 32,
    }

    provider = VaultWebhookSigningSecretProvider(vault)

    result = await provider.get_secret(
        tenant_id=tenant_id,
        subscription=subscription,
    )

    assert result.value == "s" * 32

    vault.read_secret.assert_awaited_once_with(path=reference)


@pytest.mark.asyncio
async def test_cross_tenant_webhook_vault_reference_is_rejected() -> None:
    tenant_id = uuid4()
    other_tenant_id = uuid4()
    subscription_id = uuid4()

    subscription = OutgoingWebhookSubscription(
        id=subscription_id,
        tenant_id=tenant_id,
        name="ERP",
        endpoint_url=("https://example.com/hooks"),
        event_types_json=["message.received"],
        vault_secret_reference=(
            "whatsapp-platform/"
            f"tenants/{other_tenant_id}/"
            f"webhooks/{subscription_id}/"
            f"signing/{uuid4()}"
        ),
        active=True,
    )

    vault = AsyncMock(spec=VaultClient)

    provider = VaultWebhookSigningSecretProvider(vault)

    with pytest.raises(WebhookSigningSecretInvalidError):
        await provider.get_secret(
            tenant_id=tenant_id,
            subscription=subscription,
        )

    vault.read_secret.assert_not_awaited()
