from unittest.mock import MagicMock

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.security_access_log import (
    SecurityAccessOutcome,
    SecurityPrincipalType,
)
from app.repositories.security_access_log import (
    SecurityAccessLogRepository,
)


def test_security_repository_strips_query_parameters() -> None:
    session = MagicMock(
        spec=AsyncSession,
    )

    repository = SecurityAccessLogRepository(
        session=session,
    )

    audit_log = repository.add_event(
        principal_type=(SecurityPrincipalType.HUMAN),
        principal_id="keycloak-user-1",
        event="authorization.denied",
        outcome=SecurityAccessOutcome.DENIED,
        trace_id="trace-security-1",
        request_method="get",
        request_path=("/api/v1/media/123?access_token=secret"),
        reason_code="ACCESS_DENIED",
    )

    assert audit_log.request_method == "GET"

    assert audit_log.request_path == ("/api/v1/media/123")

    assert audit_log.outcome is (SecurityAccessOutcome.DENIED)

    session.add.assert_called_once_with(audit_log)
