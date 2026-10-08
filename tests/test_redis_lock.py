from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.redis_lock import (
    RedisLockBackendUnavailableError,
    RedisShortLock,
)


def _redis_mock() -> AsyncMock:
    return AsyncMock(
        spec=Redis,
    )


@pytest.mark.asyncio
async def test_short_lock_acquires_with_expiry() -> None:
    redis = _redis_mock()
    redis.set = AsyncMock(
        return_value=True,
    )

    token = await RedisShortLock(redis).acquire(
        key="tenant:test:lock:item:key",
        ttl_seconds=15,
    )

    assert token

    redis.set.assert_awaited_once()

    call = redis.set.await_args

    assert call.args[0] == ("tenant:test:lock:item:key")
    assert call.args[1] == token
    assert call.kwargs["ex"] == 15
    assert call.kwargs["nx"] is True


@pytest.mark.asyncio
async def test_short_lock_returns_none_when_already_held() -> None:
    redis = _redis_mock()
    redis.set = AsyncMock(
        return_value=None,
    )

    token = await RedisShortLock(redis).acquire(
        key="tenant:test:lock:item:key",
        ttl_seconds=15,
    )

    assert token is None

    redis.set.assert_awaited_once()


@pytest.mark.asyncio
async def test_short_lock_release_is_owner_safe() -> None:
    redis = _redis_mock()
    redis.eval = AsyncMock(
        return_value=1,
    )

    released = await RedisShortLock(redis).release(
        key="tenant:test:lock:item:key",
        token="owner-token",
    )

    assert released is True

    redis.eval.assert_awaited_once()


@pytest.mark.asyncio
async def test_short_lock_release_rejects_wrong_owner() -> None:
    redis = _redis_mock()
    redis.eval = AsyncMock(
        return_value=0,
    )

    released = await RedisShortLock(redis).release(
        key="tenant:test:lock:item:key",
        token="wrong-owner-token",
    )

    assert released is False

    redis.eval.assert_awaited_once()


@pytest.mark.asyncio
async def test_short_lock_fails_closed_when_redis_fails() -> None:
    redis = _redis_mock()
    redis.set = AsyncMock(
        side_effect=RedisError("redis unavailable"),
    )

    with pytest.raises(RedisLockBackendUnavailableError):
        await RedisShortLock(redis).acquire(
            key="tenant:test:lock:item:key",
            ttl_seconds=15,
        )

    redis.set.assert_awaited_once()
