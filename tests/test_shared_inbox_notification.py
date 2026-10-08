from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.conversation import (
    Conversation,
    ConversationState,
)
from app.repositories.conversation import ConversationRepository
from app.services.shared_inbox import SharedInboxService


@pytest.mark.asyncio
async def test_queued_conversation_creates_notification_event() -> None:
    tenant_id = uuid4()
    group_id = uuid4()
    conversation_id = uuid4()

    employee_one_id = uuid4()
    employee_two_id = uuid4()

    session = AsyncMock(spec=AsyncSession)
    repository = AsyncMock(spec=ConversationRepository)

    repository.list_eligible_team_member_ids.return_value = [
        employee_one_id,
        employee_two_id,
    ]

    conversation = Conversation(
        id=conversation_id,
        tenant_id=tenant_id,
        whatsapp_number_id=uuid4(),
        customer_contact_id=uuid4(),
        group_id=group_id,
        state=ConversationState.QUEUED,
    )

    service = SharedInboxService(
        session=session,
        conversation_repository=repository,
    )

    event = await service.notify_eligible_team_members(
        conversation,
    )

    assert event is not None

    assert event.tenant_id == tenant_id
    assert event.event_type == "conversation.queued"
    assert event.aggregate_type == "conversation"
    assert event.aggregate_id == str(conversation_id)

    assert event.payload_json == {
        "conversation_id": str(conversation_id),
        "group_id": str(group_id),
        "recipient_employee_ids": [
            str(employee_one_id),
            str(employee_two_id),
        ],
    }

    repository.list_eligible_team_member_ids.assert_awaited_once_with(
        group_id,
    )

    session.add.assert_called_once_with(event)
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_no_event_when_conversation_has_no_group() -> None:
    session = AsyncMock(spec=AsyncSession)
    repository = AsyncMock(spec=ConversationRepository)

    conversation = Conversation(
        id=uuid4(),
        tenant_id=uuid4(),
        whatsapp_number_id=uuid4(),
        customer_contact_id=uuid4(),
        group_id=None,
        state=ConversationState.QUEUED,
    )

    service = SharedInboxService(
        session=session,
        conversation_repository=repository,
    )

    event = await service.notify_eligible_team_members(
        conversation,
    )

    assert event is None

    repository.list_eligible_team_member_ids.assert_not_awaited()
    session.add.assert_not_called()
    session.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_no_event_when_group_has_no_eligible_members() -> None:
    session = AsyncMock(spec=AsyncSession)
    repository = AsyncMock(spec=ConversationRepository)

    repository.list_eligible_team_member_ids.return_value = []

    group_id = uuid4()

    conversation = Conversation(
        id=uuid4(),
        tenant_id=uuid4(),
        whatsapp_number_id=uuid4(),
        customer_contact_id=uuid4(),
        group_id=group_id,
        state=ConversationState.QUEUED,
    )

    service = SharedInboxService(
        session=session,
        conversation_repository=repository,
    )

    event = await service.notify_eligible_team_members(
        conversation,
    )

    assert event is None

    repository.list_eligible_team_member_ids.assert_awaited_once_with(
        group_id,
    )

    session.add.assert_not_called()
    session.flush.assert_not_awaited()
