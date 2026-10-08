from __future__ import annotations

from redis.asyncio import Redis


def create_redis_client(
    redis_url: str,
) -> Redis:
    return Redis.from_url(
        redis_url,
        decode_responses=True,
        health_check_interval=30,
        socket_connect_timeout=2,
        socket_timeout=2,
        retry_on_timeout=False,
        client_name="whatsapp-platform",
    )
