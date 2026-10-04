from __future__ import annotations

from typing import cast

from fastapi import Request
from redis.asyncio import Redis


def get_redis(
    request: Request,
) -> Redis:
    redis = getattr(
        request.app.state,
        "redis",
        None,
    )

    if redis is None:
        raise RuntimeError("Redis client is not initialized.")

    return cast(Redis, redis)
