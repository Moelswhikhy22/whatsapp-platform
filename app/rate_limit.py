from __future__ import annotations

from dataclasses import dataclass

from redis.asyncio import Redis
from redis.exceptions import RedisError


_FIXED_WINDOW_SCRIPT = """
local current = redis.call("INCR", KEYS[1])

if current == 1 then
    redis.call("EXPIRE", KEYS[1], ARGV[1])
end

local ttl = redis.call("TTL", KEYS[1])

if ttl < 0 then
    redis.call("EXPIRE", KEYS[1], ARGV[1])
    ttl = tonumber(ARGV[1])
end

return {current, ttl}
"""


class RateLimitBackendUnavailableError(RuntimeError):
    pass


@dataclass(
    frozen=True,
    slots=True,
)
class RateLimitDecision:
    allowed: bool
    limit: int
    remaining: int
    retry_after_seconds: int


class FixedWindowRateLimiter:
    def __init__(
        self,
        redis: Redis,
    ) -> None:
        self._redis = redis

    async def check(
        self,
        *,
        key: str,
        limit: int,
        window_seconds: int,
    ) -> RateLimitDecision:
        if limit <= 0:
            raise ValueError("Rate limit must be greater than zero.")

        if window_seconds <= 0:
            raise ValueError("Rate-limit window must be greater than zero.")

        try:
            raw_result = await self._redis.eval(
                _FIXED_WINDOW_SCRIPT,
                1,
                key,
                window_seconds,
            )
        except RedisError as exc:
            raise RateLimitBackendUnavailableError(
                "Redis rate-limit backend is unavailable."
            ) from exc

        if not isinstance(raw_result, (list, tuple)) or len(raw_result) != 2:
            raise RateLimitBackendUnavailableError(
                "Redis rate-limit backend returned an invalid response."
            )

        try:
            current = int(raw_result[0])
            ttl = max(
                1,
                int(raw_result[1]),
            )
        except (TypeError, ValueError) as exc:
            raise RateLimitBackendUnavailableError(
                "Redis rate-limit backend returned an invalid response."
            ) from exc

        remaining = max(
            0,
            limit - current,
        )

        return RateLimitDecision(
            allowed=current <= limit,
            limit=limit,
            remaining=remaining,
            retry_after_seconds=ttl,
        )
