from __future__ import annotations

from app.db.models.message import (
    MessageStatus,
)


_STATUS_RANK: dict[
    MessageStatus,
    int,
] = {
    MessageStatus.PENDING: 0,
    MessageStatus.FAILED: 1,
    MessageStatus.SENT: 2,
    MessageStatus.DELIVERED: 3,
    MessageStatus.READ: 4,
}


def message_status_rank(
    status: MessageStatus,
) -> int:
    return _STATUS_RANK[status]


def should_advance_message_status(
    *,
    current: MessageStatus | None,
    incoming: MessageStatus,
) -> bool:
    if current is None:
        return True

    return message_status_rank(incoming) > message_status_rank(current)
