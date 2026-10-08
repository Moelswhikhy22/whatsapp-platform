from __future__ import annotations

from app.db.models.conversation import ConversationState


class InvalidConversationStateTransitionError(ValueError):
    """Raised when a conversation state transition is not allowed."""


_ALLOWED_TRANSITIONS: dict[
    ConversationState,
    frozenset[ConversationState],
] = {
    ConversationState.QUEUED: frozenset(
        {
            ConversationState.CLAIMED,
        }
    ),
    ConversationState.CLAIMED: frozenset(
        {
            ConversationState.OPEN,
            ConversationState.WAITING_CUSTOMER,
            ConversationState.WAITING_TEAM,
            ConversationState.CLOSED,
        }
    ),
    ConversationState.OPEN: frozenset(
        {
            ConversationState.WAITING_CUSTOMER,
            ConversationState.WAITING_TEAM,
            ConversationState.CLOSED,
        }
    ),
    ConversationState.WAITING_CUSTOMER: frozenset(
        {
            ConversationState.OPEN,
            ConversationState.WAITING_TEAM,
            ConversationState.CLOSED,
        }
    ),
    ConversationState.WAITING_TEAM: frozenset(
        {
            ConversationState.OPEN,
            ConversationState.WAITING_CUSTOMER,
            ConversationState.CLOSED,
        }
    ),
    ConversationState.CLOSED: frozenset(
        {
            ConversationState.REOPENED,
        }
    ),
    ConversationState.REOPENED: frozenset(
        {
            ConversationState.OPEN,
            ConversationState.WAITING_CUSTOMER,
            ConversationState.WAITING_TEAM,
            ConversationState.CLOSED,
        }
    ),
}


def can_transition_conversation_state(
    current_state: ConversationState,
    target_state: ConversationState,
) -> bool:
    return target_state in _ALLOWED_TRANSITIONS[current_state]


def require_conversation_state_transition(
    current_state: ConversationState,
    target_state: ConversationState,
) -> None:
    if can_transition_conversation_state(
        current_state,
        target_state,
    ):
        return

    raise InvalidConversationStateTransitionError(
        (f"Invalid conversation state transition: {current_state.value} -> {target_state.value}")
    )


def state_after_inbound_customer_message(
    current_state: ConversationState,
) -> ConversationState:
    if current_state is ConversationState.CLOSED:
        return ConversationState.REOPENED

    return current_state
