from __future__ import annotations

from dataclasses import dataclass

from redis.asyncio import Redis

from app.rate_limit import (
    FixedWindowRateLimiter,
    RateLimitDecision,
)
from app.redis_keys import RedisKeys


@dataclass(
    frozen=True,
    slots=True,
)
class HumanSessionRateLimitPolicy:
    limit: int = 300
    window_seconds: int = 60
    bucket: str = "human_session"


class HumanSessionRateLimiter:
    def __init__(
        self,
        redis: Redis,
        *,
        policy: HumanSessionRateLimitPolicy | None = None,
    ) -> None:
        self._redis = redis
        self._policy = policy or HumanSessionRateLimitPolicy()

    async def check(
        self,
        *,
        session_id: str,
    ) -> RateLimitDecision:
        key = RedisKeys.global_rate_limit(
            bucket=self._policy.bucket,
            identity=session_id,
        )

        return await FixedWindowRateLimiter(self._redis).check(
            key=key,
            limit=self._policy.limit,
            window_seconds=(self._policy.window_seconds),
        )
