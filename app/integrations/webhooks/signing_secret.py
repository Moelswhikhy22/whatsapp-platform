from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.db.models.outgoing_webhook import (
    OutgoingWebhookSubscription,
)
from app.integrations.vault.cache import (
    VaultSecretCache,
)
from app.integrations.vault.client import (
    VaultClient,
)


class WebhookSigningSecretError(RuntimeError):
    pass


class WebhookSigningSecretInvalidError(WebhookSigningSecretError):
    pass


class WebhookSigningSecretUnavailableError(WebhookSigningSecretError):
    pass


@dataclass(
    frozen=True,
    slots=True,
)
class WebhookSigningSecret:
    value: str


class VaultWebhookSigningSecretProvider:
    def __init__(
        self,
        vault_client: VaultClient,
        *,
        path_root: str = "whatsapp-platform",
        cache: VaultSecretCache | None = None,
        cache_ttl_seconds: int = 60,
    ) -> None:
        self._vault_client = vault_client

        self._path_root = path_root.strip().strip("/")

        if not self._path_root:
            raise ValueError("Vault path root must not be blank.")

        self._cache = (
            cache if cache is not None else VaultSecretCache(ttl_seconds=(cache_ttl_seconds))
        )

    async def get_secret(
        self,
        *,
        tenant_id: UUID,
        subscription: (OutgoingWebhookSubscription),
    ) -> WebhookSigningSecret:
        if subscription.tenant_id != tenant_id:
            raise (
                WebhookSigningSecretInvalidError(
                    ("Webhook subscription belongs to another tenant.")
                )
            )

        reference = subscription.vault_secret_reference.strip().strip("/")

        if not reference:
            raise (
                WebhookSigningSecretInvalidError(
                    ("Webhook subscription has an empty Vault secret reference.")
                )
            )

        expected_prefix = (
            f"{self._path_root}/tenants/{tenant_id}/webhooks/{subscription.id}/signing/"
        )

        if not reference.startswith(expected_prefix):
            raise (
                WebhookSigningSecretInvalidError(
                    (
                        "Webhook Vault reference "
                        "is outside the expected "
                        "tenant subscription "
                        "namespace."
                    )
                )
            )

        async def loader(
            path: str,
        ) -> dict[str, Any]:
            return await self._vault_client.read_secret(path=path)

        try:
            secret = await self._cache.get_or_load(
                path=reference,
                loader=loader,
            )

        except Exception as exc:
            raise (
                WebhookSigningSecretUnavailableError(
                    ("Webhook signing secret could not be read from Vault.")
                )
            ) from exc

        raw_value = secret.get("signing_secret")

        if (
            not isinstance(
                raw_value,
                str,
            )
            or len(raw_value.strip()) < 32
        ):
            raise (
                WebhookSigningSecretInvalidError(
                    ("Webhook Vault secret does not contain a valid signing_secret.")
                )
            )

        return WebhookSigningSecret(value=raw_value.strip())
