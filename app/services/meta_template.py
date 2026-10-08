from __future__ import annotations

from collections.abc import Mapping
from uuid import UUID

from app.authorization.context import AuthorizationContext
from app.authorization.errors import AuthorizationDeniedError
from app.authorization.template import (
    TemplateAccessResource,
    TemplateAction,
    TemplateType as AuthorizationTemplateType,
    can_manage_templates,
)
from app.authorization.tenant_isolation import TenantIsolationError
from app.db.models.template import (
    Template,
    TemplateStatus,
    TemplateType,
)
from app.repositories.template import TemplateRepository


class MetaTemplateError(RuntimeError):
    pass


class MetaTemplateNotFoundError(MetaTemplateError):
    pass


class MetaTemplateNotAllowedError(MetaTemplateError):
    pass


class MetaTemplateIntegrationNotFoundError(MetaTemplateError):
    pass


class MetaTemplateIdentityConflictError(MetaTemplateError):
    pass


class MetaTemplateInvalidDraftError(MetaTemplateError):
    pass


class MetaTemplateInvalidStateError(MetaTemplateError):
    pass


class MetaTemplateService:
    _UPDATABLE_FIELDS = frozenset(
        {
            "meta_account_id",
            "meta_template_name",
            "language",
            "category",
            "components",
        }
    )

    def __init__(
        self,
        repository: TemplateRepository,
    ) -> None:
        self._repository = repository

    async def list_meta(
        self,
        *,
        context: AuthorizationContext,
        template_status: TemplateStatus | None = None,
        meta_account_id: UUID | None = None,
    ) -> list[Template]:
        self._authorize(
            context=context,
            action=TemplateAction.READ,
        )

        return await self._repository.list_meta(
            template_status=template_status,
            meta_account_id=meta_account_id,
        )

    async def get_meta(
        self,
        *,
        template_id: UUID,
        context: AuthorizationContext,
    ) -> Template:
        template = await self._repository.get_meta(template_id)

        if template is None:
            raise MetaTemplateNotFoundError

        self._authorize(
            context=context,
            action=TemplateAction.READ,
        )

        return template

    async def create_draft(
        self,
        *,
        context: AuthorizationContext,
        meta_account_id: UUID,
        meta_template_name: str,
        language: str,
        category: str,
        components: list[dict[str, object]],
    ) -> Template:
        self._authorize(
            context=context,
            action=TemplateAction.CREATE,
        )

        self._validate_non_empty(
            meta_template_name,
            language,
            category,
        )
        self._validate_components(components)

        integration = await self._repository.get_active_meta_integration(meta_account_id)

        if integration is None:
            raise MetaTemplateIntegrationNotFoundError

        existing = await self._repository.get_meta_by_identity(
            meta_account_id=meta_account_id,
            meta_template_name=meta_template_name,
            language=language,
        )

        if existing is not None:
            raise MetaTemplateIdentityConflictError

        template = self._repository.add_meta_draft(
            meta_account_id=meta_account_id,
            meta_template_name=meta_template_name,
            language=language,
            category=category,
            components=components,
        )

        self._repository.add_template_audit(
            template_id=template.id,
            actor_id=context.actor_id,
            action="template.created",
            before=None,
            after=self._snapshot(template),
        )

        return template

    async def update_draft(
        self,
        *,
        template_id: UUID,
        context: AuthorizationContext,
        changes: Mapping[str, object],
    ) -> Template:
        if not changes:
            raise MetaTemplateInvalidDraftError

        if set(changes) - self._UPDATABLE_FIELDS:
            raise MetaTemplateInvalidDraftError

        template = await self._repository.get_meta(template_id)

        if template is None:
            raise MetaTemplateNotFoundError

        self._authorize(
            context=context,
            action=TemplateAction.UPDATE,
        )

        if template.status is not TemplateStatus.DRAFT:
            raise MetaTemplateInvalidStateError

        if (
            template.meta_account_id is None
            or template.meta_template_name is None
            or template.language is None
            or template.components_json is None
        ):
            raise RuntimeError("Meta template has an invalid persisted shape.")

        target_account_id = template.meta_account_id
        target_name = template.meta_template_name
        target_language = template.language

        if "meta_account_id" in changes:
            raw_account_id = changes["meta_account_id"]

            if not isinstance(raw_account_id, UUID):
                raise MetaTemplateInvalidDraftError

            integration = await self._repository.get_active_meta_integration(raw_account_id)

            if integration is None:
                raise (MetaTemplateIntegrationNotFoundError)

            target_account_id = raw_account_id

        if "meta_template_name" in changes:
            raw_name = changes["meta_template_name"]

            if not isinstance(raw_name, str):
                raise MetaTemplateInvalidDraftError

            target_name = raw_name.strip()

            if not target_name:
                raise MetaTemplateInvalidDraftError

        if "language" in changes:
            raw_language = changes["language"]

            if not isinstance(raw_language, str):
                raise MetaTemplateInvalidDraftError

            target_language = raw_language.strip()

            if not target_language:
                raise MetaTemplateInvalidDraftError

        identity_changed = (
            target_account_id != template.meta_account_id
            or target_name != template.meta_template_name
            or target_language != template.language
        )

        if identity_changed:
            existing = await self._repository.get_meta_by_identity(
                meta_account_id=(target_account_id),
                meta_template_name=(target_name),
                language=target_language,
            )

            if existing is not None and existing.id != template.id:
                raise (MetaTemplateIdentityConflictError)

        before = self._snapshot(template)

        template.meta_account_id = target_account_id
        template.meta_template_name = target_name
        template.language = target_language

        if "category" in changes:
            raw_category = changes["category"]

            if not isinstance(
                raw_category,
                str,
            ):
                raise MetaTemplateInvalidDraftError

            normalized_category = raw_category.strip()

            if not normalized_category:
                raise MetaTemplateInvalidDraftError

            template.category = normalized_category

        if "components" in changes:
            raw_components = changes["components"]

            if not isinstance(
                raw_components,
                list,
            ):
                raise MetaTemplateInvalidDraftError

            if not all(isinstance(item, dict) for item in raw_components):
                raise MetaTemplateInvalidDraftError

            components = [dict(item) for item in raw_components]

            self._validate_components(components)

            template.components_json = components

        self._repository.add_template_audit(
            template_id=template.id,
            actor_id=context.actor_id,
            action="template.updated",
            before=before,
            after=self._snapshot(template),
        )

        return template

    def _authorize(
        self,
        *,
        context: AuthorizationContext,
        action: TemplateAction,
    ) -> None:
        resource = TemplateAccessResource(
            tenant_id=self._repository.tenant_id,
            template_type=(AuthorizationTemplateType.META),
        )

        try:
            allowed = can_manage_templates(
                context,
                resource,
                action,
            )
        except (
            AuthorizationDeniedError,
            TenantIsolationError,
        ) as exc:
            raise MetaTemplateNotAllowedError from exc

        if not allowed:
            raise MetaTemplateNotAllowedError

    @staticmethod
    def _validate_non_empty(
        *values: str,
    ) -> None:
        if any(not value.strip() for value in values):
            raise MetaTemplateInvalidDraftError

    @staticmethod
    def _validate_components(
        components: list[dict[str, object]],
    ) -> None:
        if not components:
            raise MetaTemplateInvalidDraftError

        for component in components:
            raw_type = component.get("type")

            if not isinstance(raw_type, str) or not raw_type.strip():
                raise MetaTemplateInvalidDraftError

    @staticmethod
    def _snapshot(
        template: Template,
    ) -> dict[str, object]:
        if (
            template.template_type is not TemplateType.META
            or template.meta_template_name is None
            or template.language is None
            or template.components_json is None
            or template.status is None
            or template.meta_account_id is None
        ):
            raise RuntimeError("Meta template has an invalid persisted shape.")

        return {
            "template_type": (template.template_type.value),
            "meta_template_name": (template.meta_template_name),
            "language": template.language,
            "category": template.category,
            "components": list(template.components_json),
            "status": template.status.value,
            "meta_account_id": str(template.meta_account_id),
        }
