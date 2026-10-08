from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.business_audit_log import (
    BusinessAuditActorType,
    BusinessAuditLog,
)
from app.db.models.security_access_log import (
    SecurityAccessLog,
    SecurityAccessOutcome,
    SecurityPrincipalType,
)


class BusinessAuditQueryRepository:
    def __init__(
        self,
        *,
        session: AsyncSession,
        tenant_id: UUID,
    ) -> None:
        self._session = session
        self._tenant_id = tenant_id

    async def list_events(
        self,
        *,
        actor_type: BusinessAuditActorType | None = None,
        actor_id: str | None = None,
        action: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        trace_id: str | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[BusinessAuditLog]:
        statement: Select[BusinessAuditLog] = select(BusinessAuditLog).where(
            BusinessAuditLog.tenant_id == self._tenant_id
        )

        if actor_type is not None:
            statement = statement.where(BusinessAuditLog.actor_type == actor_type)

        if actor_id is not None:
            statement = statement.where(BusinessAuditLog.actor_id == actor_id)

        if action is not None:
            statement = statement.where(BusinessAuditLog.action == action)

        if resource_type is not None:
            statement = statement.where(BusinessAuditLog.resource_type == resource_type)

        if resource_id is not None:
            statement = statement.where(BusinessAuditLog.resource_id == resource_id)

        if trace_id is not None:
            statement = statement.where(BusinessAuditLog.trace_id == trace_id)

        if created_from is not None:
            statement = statement.where(BusinessAuditLog.created_at >= created_from)

        if created_to is not None:
            statement = statement.where(BusinessAuditLog.created_at <= created_to)

        statement = (
            statement.order_by(
                BusinessAuditLog.created_at.desc(),
                BusinessAuditLog.id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )

        result = await self._session.scalars(statement)

        return list(result.all())


class SecurityAccessQueryRepository:
    def __init__(
        self,
        *,
        session: AsyncSession,
        tenant_id: UUID,
    ) -> None:
        self._session = session
        self._tenant_id = tenant_id

    async def list_events(
        self,
        *,
        principal_type: SecurityPrincipalType | None = None,
        principal_id: str | None = None,
        event: str | None = None,
        outcome: SecurityAccessOutcome | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        reason_code: str | None = None,
        trace_id: str | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[SecurityAccessLog]:
        statement: Select[SecurityAccessLog] = select(SecurityAccessLog).where(
            SecurityAccessLog.tenant_id == self._tenant_id
        )

        if principal_type is not None:
            statement = statement.where(SecurityAccessLog.principal_type == principal_type)

        if principal_id is not None:
            statement = statement.where(SecurityAccessLog.principal_id == principal_id)

        if event is not None:
            statement = statement.where(SecurityAccessLog.event == event)

        if outcome is not None:
            statement = statement.where(SecurityAccessLog.outcome == outcome)

        if resource_type is not None:
            statement = statement.where(SecurityAccessLog.resource_type == resource_type)

        if resource_id is not None:
            statement = statement.where(SecurityAccessLog.resource_id == resource_id)

        if reason_code is not None:
            statement = statement.where(SecurityAccessLog.reason_code == reason_code)

        if trace_id is not None:
            statement = statement.where(SecurityAccessLog.trace_id == trace_id)

        if created_from is not None:
            statement = statement.where(SecurityAccessLog.created_at >= created_from)

        if created_to is not None:
            statement = statement.where(SecurityAccessLog.created_at <= created_to)

        statement = (
            statement.order_by(
                SecurityAccessLog.created_at.desc(),
                SecurityAccessLog.id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )

        result = await self._session.scalars(statement)

        return list(result.all())
