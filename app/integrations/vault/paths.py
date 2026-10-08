from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.db.models.integration import IntegrationProvider


@dataclass(frozen=True, slots=True)
class VaultPathBuilder:
    root: str = "whatsapp-platform"

    def tenant_integration_credentials(
        self,
        *,
        tenant_id: UUID,
        provider: IntegrationProvider,
        integration_id: UUID,
        rotation_id: UUID,
    ) -> str:
        root = self.root.strip().strip("/")

        if not root:
            raise ValueError("Vault path root must not be blank.")

        return (
            f"{root}/tenants/{tenant_id}/"
            f"{provider.value}/{integration_id}/"
            f"credentials/{rotation_id}"
        )

    def outgoing_webhook_signing_secret(
        self,
        *,
        tenant_id: UUID,
        subscription_id: UUID,
        secret_version_id: UUID,
    ) -> str:
        root = self.root.strip().strip("/")

        if not root:
            raise ValueError("Vault path root must not be blank.")

        return f"{root}/tenants/{tenant_id}/webhooks/{subscription_id}/signing/{secret_version_id}"
