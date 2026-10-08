from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from app.authorization.context import (
    AuthorizationContext,
)
from app.authorization.errors import (
    AuthorizationDeniedError,
)
from app.authorization.template import (
    TemplateAccessResource,
    TemplateAction,
    TemplateType as AuthorizationTemplateType,
    can_manage_templates,
)
from app.authorization.tenant_isolation import (
    TenantIsolationError,
)
from app.db.models.integration import (
    Integration,
)
from app.db.models.template import (
    Template,
    TemplateStatus,
    TemplateType,
)
from app.integrations.meta.outbound_credentials import (
    MetaOutboundCredentialProvider,
    MetaOutboundCredentialsInvalidError,
    MetaOutboundCredentialsUnavailableError,
)
from app.integrations.meta.template_client import (
    MetaTemplateAPIClient,
    MetaTemplateAPIPermanentError,
    MetaTemplateAPIRetryableError,
)
from app.repositories.template import (
    TemplateRepository,
)


class MetaTemplateSubmissionError(RuntimeError):
    pass


class MetaTemplateSubmissionNotFoundError(MetaTemplateSubmissionError):
    pass


class MetaTemplateSubmissionNotAllowedError(MetaTemplateSubmissionError):
    pass


class MetaTemplateSubmissionInvalidStateError(MetaTemplateSubmissionError):
    pass


class MetaTemplateSubmissionConfigurationError(MetaTemplateSubmissionError):
    pass


class MetaTemplateSubmissionRejectedError(MetaTemplateSubmissionError):
    pass


class MetaTemplateSubmissionUnavailableError(MetaTemplateSubmissionError):
    pass


@dataclass(frozen=True, slots=True)
class MetaTemplateSubmitResult:
    template: Template
    provider_template_id: str | None
    provider_status: str | None


class MetaTemplateSubmissionService:
    def __init__(
        self,
        *,
        repository: TemplateRepository,
        credential_provider: (MetaOutboundCredentialProvider),
        meta_client: MetaTemplateAPIClient,
    ) -> None:
        self._repository = repository
        self._credential_provider = credential_provider
        self._meta_client = meta_client

    async def submit(
        self,
        *,
        template_id: UUID,
        context: AuthorizationContext,
    ) -> MetaTemplateSubmitResult:
        template = await self._repository.lock_meta(template_id)

        if template is None:
            raise (MetaTemplateSubmissionNotFoundError)

        self._authorize(context)

        if template.status is not TemplateStatus.DRAFT:
            raise (MetaTemplateSubmissionInvalidStateError)

        if (
            template.meta_account_id is None
            or template.meta_template_name is None
            or template.language is None
            or template.components_json is None
        ):
            raise (MetaTemplateSubmissionConfigurationError)

        integration = await self._repository.get_active_meta_integration(template.meta_account_id)

        if integration is None:
            raise (MetaTemplateSubmissionConfigurationError)

        waba_id = self._waba_id(integration)

        graph_api_version = self._graph_api_version(integration)

        try:
            credentials = await self._credential_provider.get_credentials(integration)
        except MetaOutboundCredentialsInvalidError as exc:
            raise (MetaTemplateSubmissionConfigurationError) from exc
        except MetaOutboundCredentialsUnavailableError as exc:
            raise (MetaTemplateSubmissionUnavailableError) from exc

        try:
            provider_result = await self._meta_client.submit_template(
                graph_api_version=(graph_api_version),
                waba_id=waba_id,
                name=(template.meta_template_name),
                language=(template.language),
                category=(template.category),
                components=list(template.components_json),
                access_token=(credentials.access_token),
            )
        except MetaTemplateAPIRetryableError as exc:
            raise (MetaTemplateSubmissionUnavailableError) from exc
        except MetaTemplateAPIPermanentError as exc:
            raise (MetaTemplateSubmissionRejectedError) from exc

        before = self._snapshot(template)

        template.status = TemplateStatus.SUBMITTED

        template.last_synced_at = datetime.now(UTC)

        self._repository.add_template_audit(
            template_id=template.id,
            actor_id=context.actor_id,
            action="template.submitted",
            before=before,
            after=self._snapshot(template),
        )

        return MetaTemplateSubmitResult(
            template=template,
            provider_template_id=(provider_result.provider_template_id),
            provider_status=(provider_result.provider_status),
        )

    def _authorize(
        self,
        context: AuthorizationContext,
    ) -> None:
        resource = TemplateAccessResource(
            tenant_id=(self._repository.tenant_id),
            template_type=(AuthorizationTemplateType.META),
        )

        try:
            allowed = can_manage_templates(
                context,
                resource,
                TemplateAction.SUBMIT,
            )
        except (
            AuthorizationDeniedError,
            TenantIsolationError,
        ) as exc:
            raise (MetaTemplateSubmissionNotAllowedError) from exc

        if not allowed:
            raise (MetaTemplateSubmissionNotAllowedError)

    @staticmethod
    def _waba_id(
        integration: Integration,
    ) -> str:
        value = integration.external_account_id

        if value is None or not value.strip():
            raise (MetaTemplateSubmissionConfigurationError)

        return value.strip()

    @staticmethod
    def _graph_api_version(
        integration: Integration,
    ) -> str:
        value = integration.config_json.get("graph_api_version")

        if not isinstance(value, str) or not value.strip():
            raise (MetaTemplateSubmissionConfigurationError)

        return value.strip()

    @staticmethod
    def _snapshot(
        template: Template,
    ) -> dict[str, object]:
        if (
            template.template_type is not TemplateType.META
            or template.meta_account_id is None
            or template.meta_template_name is None
            or template.language is None
            or template.components_json is None
            or template.status is None
        ):
            raise RuntimeError(("Meta template has an invalid persisted shape."))

        return {
            "template_type": (template.template_type.value),
            "meta_account_id": str(template.meta_account_id),
            "meta_template_name": (template.meta_template_name),
            "language": template.language,
            "category": template.category,
            "components": list(template.components_json),
            "status": template.status.value,
            "last_synced_at": (
                template.last_synced_at.isoformat() if template.last_synced_at is not None else None
            ),
        }
