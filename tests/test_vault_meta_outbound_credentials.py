from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.db.models.integration import (
    Integration,
    IntegrationProvider,
)
from app.integrations.meta.outbound_credentials import (
    MetaOutboundCredentialsInvalidError,
    MetaOutboundCredentialsUnavailableError,
)
from app.integrations.meta.vault_outbound_credentials import (
    VaultMetaOutboundCredentialProvider,
)
from app.integrations.vault.client import (
    VaultClient,
)


@pytest.mark.asyncio
async def test_reads_access_token_from_tenant_vault_path() -> None:
    tenant_id = uuid4()

    integration = Integration(
        id=uuid4(),
        tenant_id=tenant_id,
        provider=IntegrationProvider.META,
        name="Meta",
        config_json={},
        vault_secret_reference=(f"whatsapp-platform/tenants/{tenant_id}/meta/main"),
        active=True,
    )

    vault_client = AsyncMock(spec=VaultClient)

    vault_client.read_secret.return_value = {
        "access_token": "token-123",
    }

    provider = VaultMetaOutboundCredentialProvider(vault_client)

    result = await provider.get_credentials(integration)

    assert result.access_token == "token-123"

    vault_client.read_secret.assert_awaited_once_with(
        path=(f"whatsapp-platform/tenants/{tenant_id}/meta/main")
    )


@pytest.mark.asyncio
async def test_cross_tenant_vault_reference_is_rejected() -> None:
    tenant_id = uuid4()
    other_tenant_id = uuid4()

    integration = Integration(
        id=uuid4(),
        tenant_id=tenant_id,
        provider=IntegrationProvider.META,
        name="Meta",
        config_json={},
        vault_secret_reference=(f"whatsapp-platform/tenants/{other_tenant_id}/meta/main"),
        active=True,
    )

    vault_client = AsyncMock(spec=VaultClient)

    provider = VaultMetaOutboundCredentialProvider(vault_client)

    with pytest.raises(MetaOutboundCredentialsInvalidError):
        await provider.get_credentials(integration)

    vault_client.read_secret.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_access_token_is_invalid() -> None:
    tenant_id = uuid4()

    integration = Integration(
        id=uuid4(),
        tenant_id=tenant_id,
        provider=IntegrationProvider.META,
        name="Meta",
        config_json={},
        vault_secret_reference=(f"whatsapp-platform/tenants/{tenant_id}/meta/main"),
        active=True,
    )

    vault_client = AsyncMock(spec=VaultClient)

    vault_client.read_secret.return_value = {}

    provider = VaultMetaOutboundCredentialProvider(vault_client)

    with pytest.raises(MetaOutboundCredentialsInvalidError):
        await provider.get_credentials(integration)


@pytest.mark.asyncio
async def test_vault_failure_is_retryable() -> None:
    tenant_id = uuid4()

    integration = Integration(
        id=uuid4(),
        tenant_id=tenant_id,
        provider=IntegrationProvider.META,
        name="Meta",
        config_json={},
        vault_secret_reference=(f"whatsapp-platform/tenants/{tenant_id}/meta/main"),
        active=True,
    )

    vault_client = AsyncMock(spec=VaultClient)

    vault_client.read_secret.side_effect = RuntimeError("vault unavailable")

    provider = VaultMetaOutboundCredentialProvider(vault_client)

    with pytest.raises(MetaOutboundCredentialsUnavailableError):
        await provider.get_credentials(integration)


@pytest.mark.asyncio
async def test_changed_vault_reference_reads_new_credentials() -> None:
    tenant_id = uuid4()
    integration_id = uuid4()

    first_reference = (
        f"whatsapp-platform/tenants/{tenant_id}/meta/{integration_id}/credentials/first"
    )

    second_reference = (
        f"whatsapp-platform/tenants/{tenant_id}/meta/{integration_id}/credentials/second"
    )

    integration = Integration(
        id=integration_id,
        tenant_id=tenant_id,
        provider=IntegrationProvider.META,
        name="Meta",
        config_json={},
        vault_secret_reference=(first_reference),
        active=True,
    )

    vault_client = AsyncMock(spec=VaultClient)

    vault_client.read_secret.side_effect = [
        {
            "access_token": "old-token",
        },
        {
            "access_token": "new-token",
        },
    ]

    provider = VaultMetaOutboundCredentialProvider(vault_client)

    first = await provider.get_credentials(integration)

    integration.vault_secret_reference = second_reference

    second = await provider.get_credentials(integration)

    assert first.access_token == ("old-token")

    assert second.access_token == ("new-token")

    assert vault_client.read_secret.await_count == 2
