from __future__ import annotations

from collections.abc import Mapping
from uuid import UUID, uuid4

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.business_audit_log import (
    BusinessAuditActorType,
    BusinessAuditLog,
)
from app.db.models.integration import (
    Integration,
    IntegrationProvider,
)
from app.db.models.template import (
    Template,
    TemplateStatus,
    TemplateType,
)
from app.audit_payload import (
    sanitize_audit_payload,
)


class TemplateRepository:
    def __init__(
        self,
        *,
        session: AsyncSession,
        tenant_id: UUID,
    ) -> None:
        self._session = session
        self._tenant_id = tenant_id

    @property
    def tenant_id(self) -> UUID:
        return self._tenant_id

    async def list_internal(
        self,
        *,
        active: bool | None = None,
    ) -> list[Template]:
        statement: Select[tuple[Template]] = (
            select(Template)
            .where(
                Template.tenant_id == self._tenant_id,
                Template.template_type == TemplateType.INTERNAL,
            )
            .order_by(
                Template.name.asc(),
                Template.id.asc(),
            )
        )

        if active is not None:
            statement = statement.where(
                Template.active.is_(active),
            )

        result = await self._session.scalars(statement)
        return list(result.all())

    async def list_meta(
        self,
        *,
        template_status: TemplateStatus | None = None,
        meta_account_id: UUID | None = None,
    ) -> list[Template]:
        statement: Select[tuple[Template]] = (
            select(Template)
            .where(
                Template.tenant_id == self._tenant_id,
                Template.template_type == TemplateType.META,
            )
            .order_by(
                Template.meta_template_name.asc(),
                Template.language.asc(),
                Template.id.asc(),
            )
        )

        if template_status is not None:
            statement = statement.where(
                Template.status == template_status,
            )

        if meta_account_id is not None:
            statement = statement.where(
                Template.meta_account_id == meta_account_id,
            )

        result = await self._session.scalars(statement)
        return list(result.all())

    async def get_internal(
        self,
        template_id: UUID,
    ) -> Template | None:
        statement: Select[tuple[Template]] = select(Template).where(
            Template.tenant_id == self._tenant_id,
            Template.id == template_id,
            Template.template_type == TemplateType.INTERNAL,
        )

        result = await self._session.scalars(statement)
        return result.first()

    async def get_meta(
        self,
        template_id: UUID,
    ) -> Template | None:
        statement: Select[tuple[Template]] = select(Template).where(
            Template.tenant_id == self._tenant_id,
            Template.id == template_id,
            Template.template_type == TemplateType.META,
        )

        result = await self._session.scalars(statement)
        return result.first()

    async def get_internal_by_name(
        self,
        name: str,
    ) -> Template | None:
        statement: Select[tuple[Template]] = select(Template).where(
            Template.tenant_id == self._tenant_id,
            Template.template_type == TemplateType.INTERNAL,
            Template.name == name,
        )

        result = await self._session.scalars(statement)
        return result.first()

    async def get_active_meta_integration(
        self,
        integration_id: UUID,
    ) -> Integration | None:
        statement: Select[tuple[Integration]] = select(Integration).where(
            Integration.tenant_id == self._tenant_id,
            Integration.id == integration_id,
            Integration.provider == IntegrationProvider.META,
            Integration.active.is_(True),
        )

        result = await self._session.scalars(statement)
        return result.first()

    async def get_meta_by_identity(
        self,
        *,
        meta_account_id: UUID,
        meta_template_name: str,
        language: str,
    ) -> Template | None:
        statement: Select[tuple[Template]] = select(Template).where(
            Template.tenant_id == self._tenant_id,
            Template.template_type == TemplateType.META,
            Template.meta_account_id == meta_account_id,
            Template.meta_template_name == meta_template_name,
            Template.language == language,
        )

        result = await self._session.scalars(statement)
        return result.first()

    def add_internal(
        self,
        *,
        name: str,
        category: str,
        body: str,
        variables: list[object],
    ) -> Template:
        template = Template(
            id=uuid4(),
            tenant_id=self._tenant_id,
            template_type=TemplateType.INTERNAL,
            category=category,
            name=name,
            body=body,
            variables_json=variables,
            active=True,
            meta_template_name=None,
            language=None,
            components_json=None,
            status=None,
            meta_account_id=None,
            last_synced_at=None,
        )

        self._session.add(template)
        return template

    def add_meta_draft(
        self,
        *,
        meta_account_id: UUID,
        meta_template_name: str,
        language: str,
        category: str,
        components: list[dict[str, object]],
    ) -> Template:
        template = Template(
            id=uuid4(),
            tenant_id=self._tenant_id,
            template_type=TemplateType.META,
            category=category,
            name=None,
            body=None,
            variables_json=None,
            active=None,
            meta_template_name=meta_template_name,
            language=language,
            components_json=components,
            status=TemplateStatus.DRAFT,
            meta_account_id=meta_account_id,
            last_synced_at=None,
        )

        self._session.add(template)
        return template

    def add_template_audit(
        self,
        *,
        template_id: UUID,
        actor_id: str,
        action: str,
        before: Mapping[str, object] | None,
        after: Mapping[str, object] | None,
    ) -> BusinessAuditLog:
        audit = BusinessAuditLog(
            id=uuid4(),
            tenant_id=self._tenant_id,
            actor_type=BusinessAuditActorType.HUMAN,
            actor_id=actor_id,
            action=action,
            resource_type="template",
            resource_id=str(template_id),
            before_json=sanitize_audit_payload(dict(before) if before is not None else None),
            after_json=sanitize_audit_payload(dict(after) if after is not None else None),
            trace_id=uuid4().hex,
        )

        self._session.add(audit)

        return audit

    async def lock_meta(
        self,
        template_id: UUID,
    ) -> Template | None:
        statement: Select[tuple[Template]] = (
            select(Template)
            .where(
                Template.tenant_id == self._tenant_id,
                Template.id == template_id,
                Template.template_type == TemplateType.META,
            )
            .with_for_update()
        )

        result = await self._session.scalars(statement)

        return result.first()

    async def list_meta_for_account_for_update(
        self,
        meta_account_id: UUID,
    ) -> list[Template]:
        statement: Select[tuple[Template]] = (
            select(Template)
            .where(
                Template.tenant_id == self._tenant_id,
                Template.template_type == TemplateType.META,
                Template.meta_account_id == meta_account_id,
            )
            .order_by(
                Template.id.asc(),
            )
            .with_for_update()
        )

        result = await self._session.scalars(statement)

        return list(result.all())
