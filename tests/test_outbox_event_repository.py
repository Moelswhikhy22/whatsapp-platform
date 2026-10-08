from unittest.mock import MagicMock
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.outbox_event import OutboxEvent
from app.repositories.outbox_event import (
    OutboxEventRepository,
)
from app.tenants.context import (
    TenantContext,
    TenantContextSource,
)


def test_outbox_repository_adds_pending_event() -> None:
    tenant_id = uuid4()

    session = MagicMock(
        spec=AsyncSession,
    )

    repository = OutboxEventRepository(
        session=session,
        tenant=TenantContext(
            tenant_id=tenant_id,
            slug="tenant-a",
            source=TenantContextSource.AUTHENTICATED_SESSION,
        ),
    )

    event = repository.add_event(
        event_type="conversation.reassigned",
        aggregate_type="conversation",
        aggregate_id="conversation-1",
        payload_json={
            "reason": "owner_unavailable",
        },
    )

    assert isinstance(event, OutboxEvent)
    assert event.tenant_id == tenant_id
    assert event.event_type == "conversation.reassigned"
    assert event.aggregate_type == "conversation"
    assert event.aggregate_id == "conversation-1"
    assert event.payload_json == {
        "reason": "owner_unavailable",
    }

    session.add.assert_called_once_with(event)
