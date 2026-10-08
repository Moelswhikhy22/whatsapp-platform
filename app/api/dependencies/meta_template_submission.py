from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

import httpx

from app.core.config import get_settings
from app.integrations.meta.outbound_credentials import (
    MetaOutboundCredentialProvider,
)
from app.integrations.meta.template_client import (
    MetaTemplateAPIClient,
)
from app.integrations.meta.vault_outbound_credentials import (
    VaultMetaOutboundCredentialProvider,
)
from app.integrations.vault.client import (
    VaultClient,
    VaultClientConfig,
)


@dataclass(frozen=True, slots=True)
class MetaTemplateSubmissionClients:
    credential_provider: MetaOutboundCredentialProvider

    meta_client: MetaTemplateAPIClient


async def get_meta_template_submission_clients() -> AsyncIterator[MetaTemplateSubmissionClients]:
    settings = get_settings()

    vault_client = VaultClient(
        VaultClientConfig(
            url=settings.vault_addr,
            token=settings.vault_token,
            namespace=(settings.vault_namespace),
            verify=settings.vault_verify,
            timeout_seconds=(settings.vault_timeout_seconds),
            kv_mount_point=(settings.vault_kv_mount_point),
        )
    )

    timeout = httpx.Timeout(settings.meta_http_timeout_seconds)

    try:
        async with httpx.AsyncClient(timeout=timeout) as http_client:
            yield MetaTemplateSubmissionClients(
                credential_provider=(VaultMetaOutboundCredentialProvider(vault_client)),
                meta_client=(MetaTemplateAPIClient(http_client)),
            )
    finally:
        await vault_client.close()
