from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.business_audit_log import (
    BusinessAuditActorType,
    BusinessAuditLog,
)
from app.db.models.conversation_assignment_history import (
    ConversationAssignmentHistory,
    ConversationAssignmentReason,
)
from app.repositories.business_audit_log import (
    BusinessAuditLogRepository,
)
from app.repositories.conversation_assignment_history import (
    ConversationAssignmentHistoryRepository,
)
from app.tenants.context import (
    TenantContext,
    TenantContextSource,
)


def test_assignment_history_repository_records_claim() -> None:
    tenant_id = uuid4()
    conversation_id = uuid4()
    employee_id = uuid4()

    session = MagicMock(
        spec=AsyncSession,
    )

    repository = ConversationAssignmentHistoryRepository(
        session=session,
        tenant=TenantContext(
            tenant_id=tenant_id,
            slug="tenant-a",
            source=(TenantContextSource.AUTHENTICATED_SESSION),
        ),
    )

    result = repository.add_claim(
        conversation_id=conversation_id,
        employee_id=employee_id,
    )

    assert isinstance(
        result,
        ConversationAssignmentHistory,
    )
    assert result.tenant_id == tenant_id
    assert result.conversation_id == conversation_id
    assert result.previous_employee_id is None
    assert result.new_employee_id == employee_id
    assert result.reason is ConversationAssignmentReason.CLAIM

    session.add.assert_called_once_with(result)


def test_business_audit_repository_records_claim() -> None:
    tenant_id = uuid4()
    conversation_id = uuid4()
    employee_id = uuid4()

    session = MagicMock(
        spec=AsyncSession,
    )

    repository = BusinessAuditLogRepository(
        session=session,
        tenant=TenantContext(
            tenant_id=tenant_id,
            slug="tenant-a",
            source=(TenantContextSource.AUTHENTICATED_SESSION),
        ),
    )

    result = repository.add_conversation_claim(
        conversation_id=conversation_id,
        employee_id=employee_id,
        actor_id="keycloak-user-123",
        trace_id="trace-123",
    )

    assert isinstance(
        result,
        BusinessAuditLog,
    )
    assert result.tenant_id == tenant_id
    assert result.actor_type is BusinessAuditActorType.HUMAN
    assert result.actor_id == "keycloak-user-123"
    assert result.action == "conversation.claimed"
    assert result.resource_type == "conversation"
    assert result.resource_id == str(
        conversation_id,
    )

    assert result.before_json == {
        "state": "queued",
        "responsible_employee_id": None,
    }

    assert result.after_json == {
        "state": "claimed",
        "responsible_employee_id": str(
            employee_id,
        ),
    }

    assert result.trace_id == "trace-123"

    session.add.assert_called_once_with(result)
