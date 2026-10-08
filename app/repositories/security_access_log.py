from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit_payload import (
    sanitize_request_path,
)
from app.db.models.security_access_log import (
    SecurityAccessLog,
    SecurityAccessOutcome,
    SecurityPrincipalType,
)


class SecurityAccessLogRepository:
    def __init__(
        self,
        *,
        session: AsyncSession,
    ) -> None:
        self._session = session

    def add_event(
        self,
        *,
        principal_type: SecurityPrincipalType,
        principal_id: str | None,
        event: str,
        outcome: SecurityAccessOutcome,
        trace_id: str,
        tenant_id: UUID | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        request_method: str | None = None,
        request_path: str | None = None,
        client_ip: str | None = None,
        user_agent: str | None = None,
        reason_code: str | None = None,
    ) -> SecurityAccessLog:
        audit_log = SecurityAccessLog(
            tenant_id=tenant_id,
            principal_type=principal_type,
            principal_id=principal_id,
            event=event,
            outcome=outcome,
            resource_type=resource_type,
            resource_id=resource_id,
            request_method=(request_method.upper() if request_method else None),
            request_path=sanitize_request_path(request_path),
            client_ip=client_ip,
            user_agent=user_agent,
            reason_code=reason_code,
            trace_id=trace_id,
        )

        self._session.add(audit_log)

        return audit_log
