from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.rate_limit import (
    FixedWindowRateLimiter,
    RateLimitBackendUnavailableError,
)


def _redis_mock() -> AsyncMock:
    return AsyncMock(
        spec=Redis,
    )


@pytest.mark.asyncio
async def test_rate_limiter_allows_with_remaining_capacity() -> None:
    redis = _redis_mock()
    redis.eval = AsyncMock(
        return_value=[3, 42],
    )

    decision = await FixedWindowRateLimiter(redis).check(
        key="tenant:test:rate_limit:test:key",
        limit=5,
        window_seconds=60,
    )

    assert decision.allowed is True
    assert decision.limit == 5
    assert decision.remaining == 2
    assert decision.retry_after_seconds == 42

    redis.eval.assert_awaited_once()


@pytest.mark.asyncio
async def test_rate_limiter_denies_after_limit() -> None:
    redis = _redis_mock()
    redis.eval = AsyncMock(
        return_value=[6, 17],
    )

    decision = await FixedWindowRateLimiter(redis).check(
        key="tenant:test:rate_limit:test:key",
        limit=5,
        window_seconds=60,
    )

    assert decision.allowed is False
    assert decision.limit == 5
    assert decision.remaining == 0
    assert decision.retry_after_seconds == 17

    redis.eval.assert_awaited_once()


@pytest.mark.asyncio
async def test_rate_limiter_fails_closed_when_redis_fails() -> None:
    redis = _redis_mock()
    redis.eval = AsyncMock(
        side_effect=RedisError("redis unavailable"),
    )

    with pytest.raises(RateLimitBackendUnavailableError):
        await FixedWindowRateLimiter(redis).check(
            key="tenant:test:rate_limit:test:key",
            limit=5,
            window_seconds=60,
        )

    redis.eval.assert_awaited_once()
