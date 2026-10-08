from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from app.authorization.context import (
    AuthorizationContext,
)
from app.authorization.integration import (
    IntegrationAccessResource,
    IntegrationAction,
    can_manage_integrations,
)
from app.db.models.integration import (
    Integration,
    IntegrationProvider,
)
from app.integrations.vault.client import (
    VaultClient,
)
from app.integrations.vault.paths import (
    VaultPathBuilder,
)
from app.repositories.business_audit_log import (
    BusinessAuditLogRepository,
)
from app.repositories.integration import (
    IntegrationRepository,
)


class IntegrationCredentialError(RuntimeError):
    pass


class IntegrationCredentialNotFoundError(IntegrationCredentialError):
    pass


class IntegrationCredentialInvalidError(IntegrationCredentialError):
    pass


class IntegrationCredentialVaultError(IntegrationCredentialError):
    pass


class IntegrationCredentialPersistenceError(IntegrationCredentialError):
    pass


@dataclass(frozen=True, slots=True)
class IntegrationCredentialRotationResult:
    integration_id: UUID
    provider: IntegrationProvider
    credentials_configured: bool


class IntegrationCredentialRotationService:
    def __init__(
        self,
        *,
        repository: IntegrationRepository,
        audit_repository: (BusinessAuditLogRepository),
        vault_client: VaultClient,
        path_builder: VaultPathBuilder,
    ) -> None:
        self._repository = repository
        self._audit_repository = audit_repository
        self._vault_client = vault_client
        self._path_builder = path_builder

    async def rotate(
        self,
        *,
        integration_id: UUID,
        context: AuthorizationContext,
        actor_id: str,
        trace_id: str,
        secret_values: dict[str, str],
    ) -> IntegrationCredentialRotationResult:
        integration = await self._repository.get_by_id(integration_id)

        if integration is None:
            raise (IntegrationCredentialNotFoundError)

        can_manage_integrations(
            context,
            IntegrationAccessResource(tenant_id=(integration.tenant_id)),
            IntegrationAction.CREDENTIALS_UPDATE,
        )

        normalized_secret = self._validate_secret(
            integration=integration,
            values=secret_values,
        )

        rotation_id = uuid4()

        reference = self._path_builder.tenant_integration_credentials(
            tenant_id=(integration.tenant_id),
            provider=(integration.provider),
            integration_id=(integration.id),
            rotation_id=rotation_id,
        )

        previously_configured = integration.vault_secret_reference is not None and bool(
            integration.vault_secret_reference.strip()
        )

        try:
            await self._vault_client.write_secret(
                path=reference,
                secret=normalized_secret,
            )

        except Exception as exc:
            raise (
                IntegrationCredentialVaultError(
                    "Integration credentials could not be written to Vault."
                )
            ) from exc

        self._repository.set_vault_secret_reference(
            integration=integration,
            reference=reference,
        )

        self._audit_repository.add_integration_credentials_rotated(
            integration_id=(integration.id),
            provider=integration.provider,
            actor_id=actor_id,
            trace_id=trace_id,
            previously_configured=(previously_configured),
        )

        try:
            await self._repository.flush()

        except Exception as exc:
            try:
                await self._vault_client.delete_latest_secret_version(path=reference)
            except Exception:
                pass

            raise (
                IntegrationCredentialPersistenceError("Credential metadata could not be persisted.")
            ) from exc

        return IntegrationCredentialRotationResult(
            integration_id=(integration.id),
            provider=(integration.provider),
            credentials_configured=True,
        )

    @staticmethod
    def _validate_secret(
        *,
        integration: Integration,
        values: dict[str, str],
    ) -> dict[str, str]:
        normalized = {key: value.strip() for key, value in values.items() if value.strip()}

        if integration.provider is IntegrationProvider.META:
            required = {
                "access_token",
                "app_secret",
                "verify_token",
            }

            allowed = required

        elif integration.provider is IntegrationProvider.ODOO:
            required = {
                "api_key",
            }

            allowed = required

        else:
            raise (IntegrationCredentialInvalidError("Unsupported integration provider."))

        unknown = set(normalized) - allowed

        if unknown:
            raise (IntegrationCredentialInvalidError("Unsupported credential fields."))

        missing = required - set(normalized)

        if missing:
            raise (
                IntegrationCredentialInvalidError("Required integration credentials are missing.")
            )

        return normalized
