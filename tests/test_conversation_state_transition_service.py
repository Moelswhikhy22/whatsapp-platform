from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.db.models.conversation import (
    Conversation,
    ConversationState,
)
from app.repositories.conversation import (
    ConversationRepository,
)
from app.services.conversation_state import (
    InvalidConversationStateTransitionError,
)
from app.services.conversation_state_transition import (
    ConversationStateConflictError,
    ConversationStateNotFoundError,
    ConversationStateTransitionService,
    ConversationStateWorkflowRequiredError,
)


def _conversation(
    state: ConversationState,
) -> Conversation:
    return Conversation(
        id=uuid4(),
        tenant_id=uuid4(),
        whatsapp_number_id=uuid4(),
        customer_contact_id=uuid4(),
        group_id=uuid4(),
        state=state,
        responsible_employee_id=uuid4(),
    )


@pytest.mark.asyncio
async def test_valid_state_transition_succeeds() -> None:
    repository = AsyncMock(
        spec=ConversationRepository,
    )

    current = _conversation(
        ConversationState.OPEN,
    )

    updated = _conversation(
        ConversationState.WAITING_CUSTOMER,
    )
    updated.id = current.id
    updated.tenant_id = current.tenant_id

    repository.get_by_id.return_value = current
    repository.atomic_transition_state.return_value = updated

    service = ConversationStateTransitionService(
        repository,
    )

    result = await service.transition(
        conversation_id=current.id,
        target_state=ConversationState.WAITING_CUSTOMER,
    )

    assert result is updated

    repository.atomic_transition_state.assert_awaited_once_with(
        conversation_id=current.id,
        expected_current_state=ConversationState.OPEN,
        target_state=ConversationState.WAITING_CUSTOMER,
    )


@pytest.mark.asyncio
async def test_invalid_state_transition_is_rejected() -> None:
    repository = AsyncMock(
        spec=ConversationRepository,
    )

    current = _conversation(
        ConversationState.CLOSED,
    )

    repository.get_by_id.return_value = current

    service = ConversationStateTransitionService(
        repository,
    )

    with pytest.raises(
        InvalidConversationStateTransitionError,
    ):
        await service.transition(
            conversation_id=current.id,
            target_state=ConversationState.OPEN,
        )

    repository.atomic_transition_state.assert_not_awaited()


@pytest.mark.asyncio
async def test_claim_requires_specialized_workflow() -> None:
    repository = AsyncMock(
        spec=ConversationRepository,
    )

    current = _conversation(
        ConversationState.QUEUED,
    )
    current.responsible_employee_id = None

    repository.get_by_id.return_value = current

    service = ConversationStateTransitionService(
        repository,
    )

    with pytest.raises(
        ConversationStateWorkflowRequiredError,
    ):
        await service.transition(
            conversation_id=current.id,
            target_state=ConversationState.CLAIMED,
        )

    repository.atomic_transition_state.assert_not_awaited()


@pytest.mark.asyncio
async def test_concurrent_state_change_returns_conflict() -> None:
    repository = AsyncMock(
        spec=ConversationRepository,
    )

    current = _conversation(
        ConversationState.OPEN,
    )

    repository.get_by_id.return_value = current
    repository.atomic_transition_state.return_value = None

    service = ConversationStateTransitionService(
        repository,
    )

    with pytest.raises(
        ConversationStateConflictError,
    ):
        await service.transition(
            conversation_id=current.id,
            target_state=ConversationState.CLOSED,
        )


@pytest.mark.asyncio
async def test_missing_conversation_is_rejected() -> None:
    repository = AsyncMock(
        spec=ConversationRepository,
    )
    repository.get_by_id.return_value = None

    service = ConversationStateTransitionService(
        repository,
    )

    with pytest.raises(
        ConversationStateNotFoundError,
    ):
        await service.transition(
            conversation_id=uuid4(),
            target_state=ConversationState.CLOSED,
        )

    repository.atomic_transition_state.assert_not_awaited()


@pytest.mark.asyncio
async def test_inbound_message_reopens_closed_conversation() -> None:
    repository = AsyncMock(
        spec=ConversationRepository,
    )

    closed = _conversation(
        ConversationState.CLOSED,
    )

    reopened = _conversation(
        ConversationState.REOPENED,
    )
    reopened.id = closed.id
    reopened.tenant_id = closed.tenant_id

    repository.get_by_id.return_value = closed
    repository.atomic_transition_state.return_value = reopened

    service = ConversationStateTransitionService(
        repository,
    )

    result = await service.handle_inbound_customer_message(
        conversation_id=closed.id,
    )

    assert result is reopened

    repository.atomic_transition_state.assert_awaited_once_with(
        conversation_id=closed.id,
        expected_current_state=ConversationState.CLOSED,
        target_state=ConversationState.REOPENED,
    )


@pytest.mark.asyncio
async def test_inbound_message_does_not_change_open_conversation() -> None:
    repository = AsyncMock(
        spec=ConversationRepository,
    )

    current = _conversation(
        ConversationState.OPEN,
    )

    repository.get_by_id.return_value = current

    service = ConversationStateTransitionService(
        repository,
    )

    result = await service.handle_inbound_customer_message(
        conversation_id=current.id,
    )

    assert result is current

    repository.atomic_transition_state.assert_not_awaited()
