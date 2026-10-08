from __future__ import annotations

import pytest

from app.db.models.conversation import ConversationState
from app.services.conversation_state import (
    InvalidConversationStateTransitionError,
    can_transition_conversation_state,
    require_conversation_state_transition,
    state_after_inbound_customer_message,
)


@pytest.mark.parametrize(
    ("current_state", "target_state"),
    [
        (
            ConversationState.QUEUED,
            ConversationState.CLAIMED,
        ),
        (
            ConversationState.CLAIMED,
            ConversationState.OPEN,
        ),
        (
            ConversationState.OPEN,
            ConversationState.WAITING_CUSTOMER,
        ),
        (
            ConversationState.OPEN,
            ConversationState.WAITING_TEAM,
        ),
        (
            ConversationState.WAITING_CUSTOMER,
            ConversationState.OPEN,
        ),
        (
            ConversationState.WAITING_TEAM,
            ConversationState.OPEN,
        ),
        (
            ConversationState.OPEN,
            ConversationState.CLOSED,
        ),
        (
            ConversationState.CLOSED,
            ConversationState.REOPENED,
        ),
        (
            ConversationState.REOPENED,
            ConversationState.OPEN,
        ),
    ],
)
def test_allowed_conversation_state_transitions(
    current_state: ConversationState,
    target_state: ConversationState,
) -> None:
    assert can_transition_conversation_state(
        current_state,
        target_state,
    )


@pytest.mark.parametrize(
    ("current_state", "target_state"),
    [
        (
            ConversationState.QUEUED,
            ConversationState.OPEN,
        ),
        (
            ConversationState.QUEUED,
            ConversationState.CLOSED,
        ),
        (
            ConversationState.CLOSED,
            ConversationState.OPEN,
        ),
        (
            ConversationState.CLOSED,
            ConversationState.QUEUED,
        ),
        (
            ConversationState.OPEN,
            ConversationState.QUEUED,
        ),
        (
            ConversationState.REOPENED,
            ConversationState.CLAIMED,
        ),
    ],
)
def test_invalid_conversation_state_transitions(
    current_state: ConversationState,
    target_state: ConversationState,
) -> None:
    assert not can_transition_conversation_state(
        current_state,
        target_state,
    )

    with pytest.raises(
        InvalidConversationStateTransitionError,
    ):
        require_conversation_state_transition(
            current_state,
            target_state,
        )


@pytest.mark.parametrize(
    "state",
    list(ConversationState),
)
def test_state_cannot_transition_to_itself(
    state: ConversationState,
) -> None:
    assert not can_transition_conversation_state(
        state,
        state,
    )


def test_closed_conversation_reopens_on_customer_message() -> None:
    result = state_after_inbound_customer_message(
        ConversationState.CLOSED,
    )

    assert result is ConversationState.REOPENED


@pytest.mark.parametrize(
    "state",
    [
        ConversationState.QUEUED,
        ConversationState.CLAIMED,
        ConversationState.OPEN,
        ConversationState.WAITING_CUSTOMER,
        ConversationState.WAITING_TEAM,
        ConversationState.REOPENED,
    ],
)
def test_customer_message_does_not_change_non_closed_state(
    state: ConversationState,
) -> None:
    assert state_after_inbound_customer_message(state) is state
