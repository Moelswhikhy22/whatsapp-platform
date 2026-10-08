from __future__ import annotations

import secrets

from redis.asyncio import Redis
from redis.exceptions import RedisError


_RELEASE_SCRIPT = """
if redis.call("GET", KEYS[1]) == ARGV[1] then
    return redis.call("DEL", KEYS[1])
end

return 0
"""


class RedisLockBackendUnavailableError(RuntimeError):
    pass


class RedisShortLock:
    def __init__(
        self,
        redis: Redis,
    ) -> None:
        self._redis = redis

    async def acquire(
        self,
        *,
        key: str,
        ttl_seconds: int,
    ) -> str | None:
        if ttl_seconds <= 0:
            raise ValueError("Lock TTL must be greater than zero.")

        token = secrets.token_urlsafe(24)

        try:
            acquired = await self._redis.set(
                key,
                token,
                ex=ttl_seconds,
                nx=True,
            )
        except RedisError as exc:
            raise RedisLockBackendUnavailableError("Redis lock backend is unavailable.") from exc

        if not acquired:
            return None

        return token

    async def release(
        self,
        *,
        key: str,
        token: str,
    ) -> bool:
        if not token:
            raise ValueError("Lock token cannot be empty.")

        try:
            result = await self._redis.eval(
                _RELEASE_SCRIPT,
                1,
                key,
                token,
            )
        except RedisError as exc:
            raise RedisLockBackendUnavailableError("Redis lock backend is unavailable.") from exc

        return int(result) == 1
