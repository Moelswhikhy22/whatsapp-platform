from unittest.mock import MagicMock
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit_payload import (
    REDACTED_AUDIT_VALUE,
)
from app.db.models.platform_audit_log import (
    PlatformAuditActorType,
)
from app.repositories.platform_audit_log import (
    PlatformAuditLogRepository,
)


def test_platform_audit_repository_redacts_secrets() -> None:
    session = MagicMock(
        spec=AsyncSession,
    )

    repository = PlatformAuditLogRepository(
        session=session,
    )

    tenant_id = uuid4()

    audit_log = repository.add_event(
        actor_type=PlatformAuditActorType.HUMAN,
        actor_id="platform-admin",
        action="tenant.updated",
        affected_tenant_id=tenant_id,
        resource_type="tenant",
        resource_id=str(tenant_id),
        before_json={
            "status": "active",
            "client_secret": "must-not-leak",
        },
        after_json={
            "status": "suspended",
        },
        trace_id="trace-platform-1",
    )

    assert audit_log.affected_tenant_id == tenant_id

    assert audit_log.before_json == {
        "status": "active",
        "client_secret": REDACTED_AUDIT_VALUE,
    }

    assert audit_log.after_json == {
        "status": "suspended",
    }

    session.add.assert_called_once_with(audit_log)
