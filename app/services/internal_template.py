from __future__ import annotations

from collections.abc import Mapping
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
from app.db.models.template import (
    Template,
    TemplateType,
)
from app.repositories.template import (
    TemplateRepository,
)


class InternalTemplateError(RuntimeError):
    pass


class InternalTemplateNotFoundError(InternalTemplateError):
    pass


class InternalTemplateNotAllowedError(InternalTemplateError):
    pass


class InternalTemplateNameConflictError(InternalTemplateError):
    pass


class InternalTemplateInvalidUpdateError(InternalTemplateError):
    pass


class InternalTemplateService:
    _UPDATABLE_FIELDS = frozenset(
        {
            "name",
            "category",
            "body",
            "variables",
            "active",
        }
    )

    def __init__(
        self,
        repository: TemplateRepository,
    ) -> None:
        self._repository = repository

    async def list_internal(
        self,
        *,
        context: AuthorizationContext,
        active: bool | None = None,
    ) -> list[Template]:
        self._authorize(
            context=context,
            action=TemplateAction.READ,
        )

        return await self._repository.list_internal(
            active=active,
        )

    async def get_internal(
        self,
        *,
        template_id: UUID,
        context: AuthorizationContext,
    ) -> Template:
        template = await self._repository.get_internal(template_id)

        if template is None:
            raise InternalTemplateNotFoundError

        self._authorize(
            context=context,
            action=TemplateAction.READ,
        )

        return template

    async def create_internal(
        self,
        *,
        context: AuthorizationContext,
        name: str,
        category: str,
        body: str,
        variables: list[object],
    ) -> Template:
        self._authorize(
            context=context,
            action=TemplateAction.CREATE,
        )

        existing = await self._repository.get_internal_by_name(name)

        if existing is not None:
            raise (InternalTemplateNameConflictError)

        template = self._repository.add_internal(
            name=name,
            category=category,
            body=body,
            variables=variables,
        )

        self._repository.add_template_audit(
            template_id=template.id,
            actor_id=context.actor_id,
            action="template.created",
            before=None,
            after=self._snapshot(template),
        )

        return template

    async def update_internal(
        self,
        *,
        template_id: UUID,
        context: AuthorizationContext,
        changes: Mapping[str, object],
    ) -> Template:
        if not changes:
            raise (InternalTemplateInvalidUpdateError)

        unknown_fields = set(changes) - self._UPDATABLE_FIELDS

        if unknown_fields:
            raise (InternalTemplateInvalidUpdateError)

        template = await self._repository.get_internal(template_id)

        if template is None:
            raise InternalTemplateNotFoundError

        self._authorize(
            context=context,
            action=TemplateAction.UPDATE,
        )

        before = self._snapshot(template)

        if "name" in changes:
            name = changes["name"]

            if not isinstance(name, str):
                raise (InternalTemplateInvalidUpdateError)

            if name != template.name:
                existing = await self._repository.get_internal_by_name(name)

                if existing is not None and existing.id != template.id:
                    raise (InternalTemplateNameConflictError)

                template.name = name

        if "category" in changes:
            category = changes["category"]

            if not isinstance(category, str):
                raise (InternalTemplateInvalidUpdateError)

            template.category = category

        if "body" in changes:
            body = changes["body"]

            if not isinstance(body, str):
                raise (InternalTemplateInvalidUpdateError)

            template.body = body

        if "variables" in changes:
            variables = changes["variables"]

            if not isinstance(variables, list):
                raise (InternalTemplateInvalidUpdateError)

            template.variables_json = variables

        if "active" in changes:
            active = changes["active"]

            if not isinstance(active, bool):
                raise (InternalTemplateInvalidUpdateError)

            template.active = active

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
            template_type=(AuthorizationTemplateType.INTERNAL),
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
            raise (InternalTemplateNotAllowedError) from exc

        if not allowed:
            raise InternalTemplateNotAllowedError

    @staticmethod
    def _snapshot(
        template: Template,
    ) -> dict[str, object]:
        if (
            template.template_type is not TemplateType.INTERNAL
            or template.name is None
            or template.body is None
            or template.variables_json is None
            or template.active is None
        ):
            raise RuntimeError(("Internal template has an invalid persisted shape."))

        return {
            "template_type": (template.template_type.value),
            "name": template.name,
            "category": template.category,
            "body": template.body,
            "variables": list(template.variables_json),
            "active": template.active,
        }
