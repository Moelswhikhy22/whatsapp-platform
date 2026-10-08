from __future__ import annotations

import json
from collections.abc import Mapping
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.redis_keys import RedisKeys


class RedisCacheBackendUnavailableError(RuntimeError):
    pass


class RedisCachePayloadError(RuntimeError):
    pass


class TenantRedisCache:
    def __init__(
        self,
        *,
        redis: Redis,
        tenant_id: UUID,
    ) -> None:
        self._redis = redis
        self._tenant_id = tenant_id

    async def get_json(
        self,
        *,
        namespace: str,
        identity: str,
    ) -> dict[str, object] | None:
        key = RedisKeys.cache(
            tenant_id=self._tenant_id,
            namespace=namespace,
            identity=identity,
        )

        try:
            raw_value = await self._redis.get(key)
        except RedisError as exc:
            raise RedisCacheBackendUnavailableError("Redis cache backend is unavailable.") from exc

        if raw_value is None:
            return None

        try:
            parsed = json.loads(raw_value)
        except (
            TypeError,
            json.JSONDecodeError,
        ) as exc:
            raise RedisCachePayloadError("Redis cache payload is invalid.") from exc

        if not isinstance(parsed, dict):
            raise RedisCachePayloadError("Redis cache payload must be an object.")

        return parsed

    async def set_json(
        self,
        *,
        namespace: str,
        identity: str,
        value: Mapping[str, object],
        ttl_seconds: int,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("Cache TTL must be greater than zero.")

        key = RedisKeys.cache(
            tenant_id=self._tenant_id,
            namespace=namespace,
            identity=identity,
        )

        payload = json.dumps(
            dict(value),
            separators=(",", ":"),
            sort_keys=True,
        )

        try:
            await self._redis.set(
                key,
                payload,
                ex=ttl_seconds,
            )
        except RedisError as exc:
            raise RedisCacheBackendUnavailableError("Redis cache backend is unavailable.") from exc

    async def invalidate(
        self,
        *,
        namespace: str,
        identity: str,
    ) -> bool:
        key = RedisKeys.cache(
            tenant_id=self._tenant_id,
            namespace=namespace,
            identity=identity,
        )

        try:
            deleted = await self._redis.delete(key)
        except RedisError as exc:
            raise RedisCacheBackendUnavailableError("Redis cache backend is unavailable.") from exc

        return int(deleted) > 0

    async def invalidate_namespace(
        self,
        *,
        namespace: str,
        scan_count: int = 200,
    ) -> int:
        if scan_count <= 0:
            raise ValueError("Redis scan count must be greater than zero.")

        prefix = RedisKeys.cache_prefix(
            tenant_id=self._tenant_id,
            namespace=namespace,
        )

        pattern = f"{prefix}:*"

        cursor: int | str = 0
        deleted_count = 0

        try:
            while True:
                cursor, keys = await self._redis.scan(
                    cursor=cursor,
                    match=pattern,
                    count=scan_count,
                )

                if keys:
                    deleted_count += int(await self._redis.delete(*keys))

                if str(cursor) == "0":
                    break
        except RedisError as exc:
            raise RedisCacheBackendUnavailableError("Redis cache backend is unavailable.") from exc

        return deleted_count
