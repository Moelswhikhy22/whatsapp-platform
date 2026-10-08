from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit_payload import (
    sanitize_audit_payload,
)
from app.db.models.platform_audit_log import (
    PlatformAuditActorType,
    PlatformAuditLog,
)


class PlatformAuditLogRepository:
    def __init__(
        self,
        *,
        session: AsyncSession,
    ) -> None:
        self._session = session

    def add_event(
        self,
        *,
        actor_type: PlatformAuditActorType,
        actor_id: str,
        action: str,
        trace_id: str,
        affected_tenant_id: UUID | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        before_json: dict[str, object] | None = None,
        after_json: dict[str, object] | None = None,
    ) -> PlatformAuditLog:
        audit_log = PlatformAuditLog(
            affected_tenant_id=affected_tenant_id,
            actor_type=actor_type,
            actor_id=actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            before_json=sanitize_audit_payload(before_json),
            after_json=sanitize_audit_payload(after_json),
            trace_id=trace_id,
        )

        self._session.add(audit_log)

        return audit_log
