from __future__ import annotations

from dataclasses import dataclass

import httpx


@dataclass(frozen=True, slots=True)
class HTTPClientConfig:
    connect_timeout_seconds: float = 5.0
    read_timeout_seconds: float = 30.0
    write_timeout_seconds: float = 30.0
    pool_timeout_seconds: float = 5.0

    max_connections: int = 100
    max_keepalive_connections: int = 20
    keepalive_expiry_seconds: float = 5.0

    follow_redirects: bool = False
    trust_env: bool = True


def create_http_client(
    config: HTTPClientConfig | None = None,
) -> httpx.AsyncClient:
    client_config = config or HTTPClientConfig()

    timeout = httpx.Timeout(
        connect=client_config.connect_timeout_seconds,
        read=client_config.read_timeout_seconds,
        write=client_config.write_timeout_seconds,
        pool=client_config.pool_timeout_seconds,
    )

    limits = httpx.Limits(
        max_connections=client_config.max_connections,
        max_keepalive_connections=(client_config.max_keepalive_connections),
        keepalive_expiry=(client_config.keepalive_expiry_seconds),
    )

    return httpx.AsyncClient(
        timeout=timeout,
        limits=limits,
        follow_redirects=client_config.follow_redirects,
        trust_env=client_config.trust_env,
    )
