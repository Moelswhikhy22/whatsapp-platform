from __future__ import annotations

import logging
from uuid import UUID, uuid4

from fastapi import Request

from app.api.dependencies.database import (
    get_session_factory,
)
from app.db.models.security_access_log import (
    SecurityAccessOutcome,
    SecurityPrincipalType,
)
from app.repositories.security_access_log import (
    SecurityAccessLogRepository,
)


logger = logging.getLogger(__name__)


def get_request_trace_id(
    request: Request,
) -> str:
    existing = getattr(
        request.state,
        "trace_id",
        None,
    )

    if isinstance(existing, str) and existing.strip():
        return existing

    trace_id = uuid4().hex

    request.state.trace_id = trace_id

    return trace_id


async def record_security_access(
    *,
    request: Request,
    principal_type: SecurityPrincipalType,
    principal_id: str | None,
    event: str,
    outcome: SecurityAccessOutcome,
    reason_code: str | None = None,
    tenant_id: UUID | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
) -> None:
    """
    Persist a security/access event independently from the
    business transaction.

    Security logging must never record Authorization headers,
    cookies, bearer tokens, session IDs, request bodies, or
    query-string values.

    Failure to persist the security event must not change the
    authentication/authorization result of the request.
    """

    trace_id = get_request_trace_id(request)

    try:
        session_factory = get_session_factory(request)

        async with session_factory() as session:
            repository = SecurityAccessLogRepository(session=session)

            repository.add_event(
                principal_type=principal_type,
                principal_id=principal_id,
                event=event,
                outcome=outcome,
                tenant_id=tenant_id,
                resource_type=resource_type,
                resource_id=resource_id,
                request_method=request.method,
                request_path=request.url.path,
                client_ip=_client_ip(request),
                user_agent=_user_agent(request),
                reason_code=reason_code,
                trace_id=trace_id,
            )

            await session.commit()

    except Exception:
        logger.exception(
            "Security access log persistence failed.",
            extra={
                "trace_id": trace_id,
                "event": event,
            },
        )


def _client_ip(
    request: Request,
) -> str | None:
    if request.client is None:
        return None

    return request.client.host


def _user_agent(
    request: Request,
) -> str | None:
    value = request.headers.get("user-agent")

    if value is None:
        return None

    sanitized = value.replace("\r", "").replace("\n", "").strip()

    if not sanitized:
        return None

    return sanitized[:1024]
