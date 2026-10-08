from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.authorization.context import (
    AuthorizationContext,
)
from app.authorization.integration import (
    IntegrationAccessResource,
    IntegrationAction,
    can_manage_integrations,
)
from app.db.models.integration import (
    IntegrationProvider,
)
from app.integrations.meta.credential_validation import (
    MetaCredentialRejectedError,
    MetaCredentialValidationClient,
    MetaCredentialValidationRetryableError,
)
from app.integrations.meta.outbound_credentials import (
    MetaOutboundCredentialProvider,
    MetaOutboundCredentialsInvalidError,
    MetaOutboundCredentialsUnavailableError,
)
from app.repositories.integration import (
    IntegrationRepository,
)


class IntegrationValidationError(RuntimeError):
    pass


class IntegrationValidationNotFoundError(IntegrationValidationError):
    pass


class IntegrationValidationConfigurationError(IntegrationValidationError):
    pass


class IntegrationValidationUnavailableError(IntegrationValidationError):
    pass


@dataclass(
    frozen=True,
    slots=True,
)
class IntegrationValidationResult:
    integration_id: UUID
    provider: IntegrationProvider
    valid: bool
    checked_resource_count: int
    code: str


class IntegrationValidationService:
    def __init__(
        self,
        *,
        repository: IntegrationRepository,
        credential_provider: (MetaOutboundCredentialProvider),
        meta_client: (MetaCredentialValidationClient),
    ) -> None:
        self._repository = repository
        self._credential_provider = credential_provider
        self._meta_client = meta_client

    async def validate(
        self,
        *,
        integration_id: UUID,
        context: AuthorizationContext,
    ) -> IntegrationValidationResult:
        integration = await self._repository.get_by_id(integration_id)

        if integration is None:
            raise (IntegrationValidationNotFoundError)

        can_manage_integrations(
            context,
            IntegrationAccessResource(tenant_id=(integration.tenant_id)),
            IntegrationAction.VALIDATE,
        )

        if integration.provider is not IntegrationProvider.META:
            raise (
                IntegrationValidationConfigurationError(
                    ("External validation for this provider is not implemented yet.")
                )
            )

        graph_api_version = self._graph_api_version(integration.config_json)

        numbers = await self._repository.list_active_whatsapp_numbers(integration.id)

        if not numbers:
            raise (
                IntegrationValidationConfigurationError(
                    ("Meta integration has no active WhatsApp numbers.")
                )
            )

        try:
            credentials = await self._credential_provider.get_credentials(integration)

        except MetaOutboundCredentialsInvalidError as exc:
            raise (
                IntegrationValidationConfigurationError(
                    ("Stored Meta credentials are incomplete or invalid.")
                )
            ) from exc

        except MetaOutboundCredentialsUnavailableError as exc:
            raise (
                IntegrationValidationUnavailableError(
                    ("Stored Meta credentials cannot currently be read.")
                )
            ) from exc

        checked = 0

        for number in numbers:
            try:
                await self._meta_client.validate_phone_number(
                    graph_api_version=(graph_api_version),
                    phone_number_id=(number.meta_phone_number_id),
                    access_token=(credentials.access_token),
                )

            except MetaCredentialRejectedError:
                return IntegrationValidationResult(
                    integration_id=(integration.id),
                    provider=(integration.provider),
                    valid=False,
                    checked_resource_count=(checked),
                    code=("META_CREDENTIAL_REJECTED"),
                )

            except MetaCredentialValidationRetryableError as exc:
                raise (
                    IntegrationValidationUnavailableError(
                        ("Meta credential validation is temporarily unavailable.")
                    )
                ) from exc

            checked += 1

        return IntegrationValidationResult(
            integration_id=integration.id,
            provider=integration.provider,
            valid=True,
            checked_resource_count=checked,
            code="VALID",
        )

    @staticmethod
    def _graph_api_version(
        config: dict[str, object],
    ) -> str:
        raw_value = config.get("graph_api_version")

        if (
            not isinstance(
                raw_value,
                str,
            )
            or not raw_value.strip()
        ):
            raise (IntegrationValidationConfigurationError(("Meta graph_api_version is missing.")))

        return raw_value.strip()
