from __future__ import annotations

from collections.abc import Callable
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
    MetaRemoteTemplate,
    MetaTemplateAPIClient,
    MetaTemplateAPIPermanentError,
    MetaTemplateAPIRetryableError,
)
from app.repositories.template import (
    TemplateRepository,
)


class MetaTemplateSyncError(RuntimeError):
    pass


class MetaTemplateSyncNotAllowedError(MetaTemplateSyncError):
    pass


class MetaTemplateSyncIntegrationNotFoundError(MetaTemplateSyncError):
    pass


class MetaTemplateSyncConfigurationError(MetaTemplateSyncError):
    pass


class MetaTemplateSyncUnavailableError(MetaTemplateSyncError):
    pass


@dataclass(frozen=True, slots=True)
class MetaTemplateSyncResult:
    fetched_count: int
    matched_count: int
    updated_count: int
    unmatched_count: int
    draft_skipped_count: int
    unknown_status_count: int


_PROVIDER_STATUS_MAP: dict[
    str,
    TemplateStatus,
] = {
    "PENDING": TemplateStatus.SUBMITTED,
    "APPROVED": TemplateStatus.APPROVED,
    "REJECTED": TemplateStatus.REJECTED,
    "PAUSED": TemplateStatus.PAUSED,
    "DISABLED": TemplateStatus.DISABLED,
}


class MetaTemplateSyncService:
    def __init__(
        self,
        *,
        repository: TemplateRepository,
        credential_provider: (MetaOutboundCredentialProvider),
        meta_client: MetaTemplateAPIClient,
        clock: Callable[
            [],
            datetime,
        ]
        | None = None,
    ) -> None:
        self._repository = repository
        self._credential_provider = credential_provider
        self._meta_client = meta_client
        self._clock = clock if clock is not None else lambda: datetime.now(UTC)

    async def sync(
        self,
        *,
        context: AuthorizationContext,
        meta_account_id: UUID,
    ) -> MetaTemplateSyncResult:
        self._authorize(context)

        integration = await self._repository.get_active_meta_integration(meta_account_id)

        if integration is None:
            raise (MetaTemplateSyncIntegrationNotFoundError)

        waba_id = self._waba_id(integration)

        graph_api_version = self._graph_api_version(integration)

        try:
            credentials = await self._credential_provider.get_credentials(integration)
        except MetaOutboundCredentialsInvalidError as exc:
            raise (MetaTemplateSyncConfigurationError) from exc
        except MetaOutboundCredentialsUnavailableError as exc:
            raise (MetaTemplateSyncUnavailableError) from exc

        try:
            remote_templates = await self._meta_client.fetch_templates(
                graph_api_version=(graph_api_version),
                waba_id=waba_id,
                access_token=(credentials.access_token),
            )
        except MetaTemplateAPIRetryableError as exc:
            raise (MetaTemplateSyncUnavailableError) from exc
        except MetaTemplateAPIPermanentError as exc:
            raise (MetaTemplateSyncConfigurationError) from exc

        local_templates = await self._repository.list_meta_for_account_for_update(meta_account_id)

        local_by_identity = {
            (
                template.meta_template_name,
                template.language,
            ): template
            for template in local_templates
            if (template.meta_template_name is not None and template.language is not None)
        }

        matched_count = 0
        updated_count = 0
        draft_skipped_count = 0
        unknown_status_count = 0

        synced_at = self._clock()

        for remote in remote_templates:
            local = local_by_identity.get(
                (
                    remote.name,
                    remote.language,
                )
            )

            if local is None:
                continue

            matched_count += 1

            if local.status is TemplateStatus.DRAFT:
                draft_skipped_count += 1
                continue

            mapped_status = self._map_status(remote)

            if mapped_status is None:
                unknown_status_count += 1
                continue

            before = self._snapshot(local)

            status_changed = local.status is not mapped_status

            local.status = mapped_status
            local.last_synced_at = synced_at

            if not status_changed:
                continue

            updated_count += 1

            self._repository.add_template_audit(
                template_id=local.id,
                actor_id=context.actor_id,
                action=("template.status_synced"),
                before=before,
                after=self._snapshot(local),
            )

        return MetaTemplateSyncResult(
            fetched_count=len(remote_templates),
            matched_count=matched_count,
            updated_count=updated_count,
            unmatched_count=(len(remote_templates) - matched_count),
            draft_skipped_count=(draft_skipped_count),
            unknown_status_count=(unknown_status_count),
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
                TemplateAction.UPDATE,
            )
        except (
            AuthorizationDeniedError,
            TenantIsolationError,
        ) as exc:
            raise (MetaTemplateSyncNotAllowedError) from exc

        if not allowed:
            raise (MetaTemplateSyncNotAllowedError)

    @staticmethod
    def _map_status(
        remote: MetaRemoteTemplate,
    ) -> TemplateStatus | None:
        return _PROVIDER_STATUS_MAP.get(remote.status.upper())

    @staticmethod
    def _waba_id(
        integration: Integration,
    ) -> str:
        value = integration.external_account_id

        if value is None or not value.strip():
            raise (MetaTemplateSyncConfigurationError)

        return value.strip()

    @staticmethod
    def _graph_api_version(
        integration: Integration,
    ) -> str:
        value = integration.config_json.get("graph_api_version")

        if not isinstance(value, str) or not value.strip():
            raise (MetaTemplateSyncConfigurationError)

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
