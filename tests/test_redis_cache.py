from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.redis_cache import (
    RedisCacheBackendUnavailableError,
    TenantRedisCache,
)


def _redis_mock() -> AsyncMock:
    return AsyncMock(
        spec=Redis,
    )


@pytest.mark.asyncio
async def test_tenant_cache_round_trip_uses_tenant_scoped_key() -> None:
    redis = _redis_mock()
    redis.set = AsyncMock(
        return_value=True,
    )
    redis.get = AsyncMock(
        return_value='{"enabled":true}',
    )

    tenant_id = uuid4()

    cache = TenantRedisCache(
        redis=redis,
        tenant_id=tenant_id,
    )

    await cache.set_json(
        namespace="tenant-context",
        identity="tenant-settings",
        value={
            "enabled": True,
        },
        ttl_seconds=60,
    )

    result = await cache.get_json(
        namespace="tenant-context",
        identity="tenant-settings",
    )

    assert result == {
        "enabled": True,
    }

    set_key = redis.set.await_args.args[0]
    get_key = redis.get.await_args.args[0]

    assert set_key == get_key
    assert set_key.startswith(f"tenant:{tenant_id}:cache:")


@pytest.mark.asyncio
async def test_cache_invalidate_namespace_deletes_only_matching_keys() -> None:
    redis = _redis_mock()
    redis.scan = AsyncMock(
        side_effect=[
            (
                7,
                [
                    "tenant:x:cache:settings:a",
                    "tenant:x:cache:settings:b",
                ],
            ),
            (
                0,
                [
                    "tenant:x:cache:settings:c",
                ],
            ),
        ]
    )
    redis.delete = AsyncMock(
        side_effect=[
            2,
            1,
        ]
    )

    cache = TenantRedisCache(
        redis=redis,
        tenant_id=uuid4(),
    )

    deleted = await cache.invalidate_namespace(
        namespace="settings",
    )

    assert deleted == 3
    assert redis.scan.await_count == 2
    assert redis.delete.await_count == 2


@pytest.mark.asyncio
async def test_cache_failure_is_not_silently_accepted() -> None:
    redis = _redis_mock()
    redis.get = AsyncMock(
        side_effect=RedisError("redis unavailable"),
    )

    cache = TenantRedisCache(
        redis=redis,
        tenant_id=uuid4(),
    )

    with pytest.raises(RedisCacheBackendUnavailableError):
        await cache.get_json(
            namespace="settings",
            identity="current",
        )
