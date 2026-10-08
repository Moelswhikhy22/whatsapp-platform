from __future__ import annotations

from uuid import UUID

from app.db.models.conversation import (
    Conversation,
    ConversationState,
)
from app.repositories.conversation import (
    ConversationRepository,
)
from app.services.conversation_state import (
    require_conversation_state_transition,
    state_after_inbound_customer_message,
)


class ConversationStateNotFoundError(Exception):
    """Raised when the conversation is outside tenant scope or missing."""


class ConversationStateConflictError(Exception):
    """Raised when the conversation changed concurrently."""


class ConversationStateWorkflowRequiredError(Exception):
    """Raised when a specialized workflow must perform the transition."""


class ConversationStateTransitionService:
    def __init__(
        self,
        repository: ConversationRepository,
    ) -> None:
        self._repository = repository

    async def transition(
        self,
        *,
        conversation_id: UUID,
        target_state: ConversationState,
    ) -> Conversation:
        conversation = await self._repository.get_by_id(
            conversation_id,
        )

        if conversation is None:
            raise ConversationStateNotFoundError

        current_state = conversation.state

        require_conversation_state_transition(
            current_state,
            target_state,
        )

        if current_state is ConversationState.QUEUED and target_state is ConversationState.CLAIMED:
            raise ConversationStateWorkflowRequiredError(
                "Use the conversation claim workflow.",
            )

        updated = await self._repository.atomic_transition_state(
            conversation_id=conversation_id,
            expected_current_state=current_state,
            target_state=target_state,
        )

        if updated is None:
            raise ConversationStateConflictError

        return updated

    async def handle_inbound_customer_message(
        self,
        *,
        conversation_id: UUID,
    ) -> Conversation:
        conversation = await self._repository.get_by_id(
            conversation_id,
        )

        if conversation is None:
            raise ConversationStateNotFoundError

        target_state = state_after_inbound_customer_message(
            conversation.state,
        )

        if target_state is conversation.state:
            return conversation

        updated = await self._repository.atomic_transition_state(
            conversation_id=conversation_id,
            expected_current_state=conversation.state,
            target_state=target_state,
        )

        if updated is None:
            raise ConversationStateConflictError

        return updated
