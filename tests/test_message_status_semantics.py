import pytest

from app.db.models.message import (
    MessageStatus,
)
from app.services.message_status_semantics import (
    message_status_rank,
    should_advance_message_status,
)


def test_semantic_rank_order() -> None:
    assert (
        message_status_rank(MessageStatus.PENDING)
        < message_status_rank(MessageStatus.FAILED)
        < message_status_rank(MessageStatus.SENT)
        < message_status_rank(MessageStatus.DELIVERED)
        < message_status_rank(MessageStatus.READ)
    )


@pytest.mark.parametrize(
    ("current", "incoming"),
    [
        (
            MessageStatus.PENDING,
            MessageStatus.SENT,
        ),
        (
            MessageStatus.SENT,
            MessageStatus.DELIVERED,
        ),
        (
            MessageStatus.DELIVERED,
            MessageStatus.READ,
        ),
        (
            MessageStatus.PENDING,
            MessageStatus.FAILED,
        ),
        (
            MessageStatus.FAILED,
            MessageStatus.SENT,
        ),
    ],
)
def test_forward_status_changes_are_allowed(
    current: MessageStatus,
    incoming: MessageStatus,
) -> None:
    assert should_advance_message_status(
        current=current,
        incoming=incoming,
    )


@pytest.mark.parametrize(
    ("current", "incoming"),
    [
        (
            MessageStatus.SENT,
            MessageStatus.FAILED,
        ),
        (
            MessageStatus.DELIVERED,
            MessageStatus.SENT,
        ),
        (
            MessageStatus.READ,
            MessageStatus.DELIVERED,
        ),
        (
            MessageStatus.READ,
            MessageStatus.FAILED,
        ),
        (
            MessageStatus.SENT,
            MessageStatus.SENT,
        ),
    ],
)
def test_regressions_and_duplicates_are_rejected(
    current: MessageStatus,
    incoming: MessageStatus,
) -> None:
    assert not should_advance_message_status(
        current=current,
        incoming=incoming,
    )


def test_none_effective_status_accepts_first_status() -> None:
    assert should_advance_message_status(
        current=None,
        incoming=MessageStatus.SENT,
    )
