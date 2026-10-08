from __future__ import annotations

from datetime import (
    UTC,
    datetime,
    timedelta,
)


CUSTOMER_SERVICE_WINDOW = timedelta(
    hours=24,
)


def is_free_text_window_open(
    *,
    last_customer_message_at: (datetime | None),
    now: datetime | None = None,
) -> bool:
    if last_customer_message_at is None:
        return False

    if last_customer_message_at.tzinfo is None:
        raise ValueError(("last_customer_message_at must be timezone-aware."))

    current = now or datetime.now(UTC)

    if current.tzinfo is None:
        raise ValueError("now must be timezone-aware.")

    if last_customer_message_at > current:
        return False

    return current - last_customer_message_at <= CUSTOMER_SERVICE_WINDOW
