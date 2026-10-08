from __future__ import annotations

from uuid import UUID

from app.db.models.integration import Integration
from app.integrations.meta.outbound_credentials import (
    MetaOutboundCredentials,
    MetaOutboundCredentialsInvalidError,
    MetaOutboundCredentialsUnavailableError,
)
from app.integrations.vault.cache import (
    VaultSecretCache,
)
from app.integrations.vault.client import (
    VaultClient,
)


class VaultMetaOutboundCredentialProvider:
    def __init__(
        self,
        vault_client: VaultClient,
        *,
        cache: VaultSecretCache | None = None,
        cache_ttl_seconds: int = 60,
    ) -> None:
        self._vault_client = vault_client

        self._cache = (
            cache if cache is not None else VaultSecretCache(ttl_seconds=cache_ttl_seconds)
        )

        self._last_references: dict[
            UUID,
            str,
        ] = {}

    async def get_credentials(
        self,
        integration: Integration,
    ) -> MetaOutboundCredentials:
        reference = integration.vault_secret_reference

        if reference is None:
            raise (
                MetaOutboundCredentialsInvalidError(
                    "Meta integration has no Vault secret reference."
                )
            )

        normalized_reference = reference.strip().strip("/")

        if not normalized_reference:
            raise (
                MetaOutboundCredentialsInvalidError(
                    "Meta integration has an empty Vault reference."
                )
            )

        expected_prefix = f"whatsapp-platform/tenants/{integration.tenant_id}/meta/"

        if not normalized_reference.startswith(expected_prefix):
            raise (
                MetaOutboundCredentialsInvalidError(
                    "Meta Vault reference is outside the tenant namespace."
                )
            )

        previous_reference = self._last_references.get(integration.id)

        if previous_reference is not None and previous_reference != normalized_reference:
            await self._cache.invalidate(previous_reference)

        self._last_references[integration.id] = normalized_reference

        try:
            secret = await self._cache.get_or_load(
                path=normalized_reference,
                loader=self._read_secret,
            )

        except Exception as exc:
            raise (
                MetaOutboundCredentialsUnavailableError(
                    "Meta credentials could not be read from Vault."
                )
            ) from exc

        raw_access_token = secret.get("access_token")

        if (
            not isinstance(
                raw_access_token,
                str,
            )
            or not raw_access_token.strip()
        ):
            raise (
                MetaOutboundCredentialsInvalidError(
                    "Meta Vault secret does not contain access_token."
                )
            )

        return MetaOutboundCredentials(access_token=(raw_access_token.strip()))

    async def _read_secret(
        self,
        path: str,
    ) -> dict[str, object]:
        return await self._vault_client.read_secret(path=path)
