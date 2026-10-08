from datetime import (
    UTC,
    datetime,
    timedelta,
)

import pytest

from app.services.meta_messaging_window import (
    is_free_text_window_open,
)


NOW = datetime(
    2026,
    10,
    12,
    14,
    0,
    tzinfo=UTC,
)


def test_window_open_inside_24_hours() -> None:
    assert is_free_text_window_open(
        last_customer_message_at=(NOW - timedelta(hours=23)),
        now=NOW,
    )


def test_window_open_at_exact_boundary() -> None:
    assert is_free_text_window_open(
        last_customer_message_at=(NOW - timedelta(hours=24)),
        now=NOW,
    )


def test_window_closed_after_24_hours() -> None:
    assert not is_free_text_window_open(
        last_customer_message_at=(
            NOW
            - timedelta(
                hours=24,
                seconds=1,
            )
        ),
        now=NOW,
    )


def test_no_customer_message_closes_window() -> None:
    assert not is_free_text_window_open(
        last_customer_message_at=None,
        now=NOW,
    )


def test_future_customer_timestamp_fails_closed() -> None:
    assert not is_free_text_window_open(
        last_customer_message_at=(NOW + timedelta(seconds=1)),
        now=NOW,
    )


def test_naive_timestamp_is_rejected() -> None:
    with pytest.raises(ValueError):
        is_free_text_window_open(
            last_customer_message_at=(
                datetime(
                    2026,
                    10,
                    12,
                    13,
                    0,
                )
            ),
            now=NOW,
        )
