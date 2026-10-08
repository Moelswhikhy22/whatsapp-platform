from __future__ import annotations

from app.api.rate_limits import (
    INTEGRATION_ADMIN_RATE_LIMIT,
    MEDIA_URL_RATE_LIMIT,
    MESSAGE_SEND_RATE_LIMIT,
)


def test_rate_limit_policies_use_distinct_buckets() -> None:
    buckets = {
        MESSAGE_SEND_RATE_LIMIT.bucket,
        MEDIA_URL_RATE_LIMIT.bucket,
        INTEGRATION_ADMIN_RATE_LIMIT.bucket,
    }

    assert len(buckets) == 3


def test_media_url_rate_limit_is_positive() -> None:
    assert MEDIA_URL_RATE_LIMIT.limit > 0
    assert MEDIA_URL_RATE_LIMIT.window_seconds > 0


def test_integration_admin_rate_limit_is_stricter_than_media() -> None:
    assert INTEGRATION_ADMIN_RATE_LIMIT.limit < MEDIA_URL_RATE_LIMIT.limit
