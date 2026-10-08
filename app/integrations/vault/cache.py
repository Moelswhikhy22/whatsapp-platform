from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any


SecretLoader = Callable[
    [str],
    Awaitable[dict[str, Any]],
]


@dataclass(frozen=True, slots=True)
class _CacheEntry:
    value: dict[str, Any]
    expires_at: float


class VaultSecretCache:
    def __init__(
        self,
        *,
        ttl_seconds: int = 60,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("Vault secret cache TTL must be greater than zero.")

        self._ttl_seconds = ttl_seconds
        self._entries: dict[
            str,
            _CacheEntry,
        ] = {}

        self._lock = asyncio.Lock()

    async def get_or_load(
        self,
        *,
        path: str,
        loader: SecretLoader,
    ) -> dict[str, Any]:
        now = time.monotonic()

        async with self._lock:
            entry = self._entries.get(path)

            if entry is not None and entry.expires_at > now:
                return dict(entry.value)

            value = await loader(path)

            self._entries[path] = _CacheEntry(
                value=dict(value),
                expires_at=(now + self._ttl_seconds),
            )

            return dict(value)

    async def invalidate(
        self,
        path: str,
    ) -> None:
        normalized = path.strip().strip("/")

        async with self._lock:
            self._entries.pop(
                normalized,
                None,
            )

    async def clear(self) -> None:
        async with self._lock:
            self._entries.clear()
