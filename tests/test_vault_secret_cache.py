from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.integrations.vault.cache import (
    VaultSecretCache,
)


@pytest.mark.asyncio
async def test_cache_reads_secret_once() -> None:
    loader = AsyncMock(
        return_value={
            "access_token": "secret",
        }
    )

    cache = VaultSecretCache(ttl_seconds=60)

    first = await cache.get_or_load(
        path="tenant/path",
        loader=loader,
    )

    second = await cache.get_or_load(
        path="tenant/path",
        loader=loader,
    )

    assert first == {"access_token": "secret"}

    assert second == first

    loader.assert_awaited_once()


@pytest.mark.asyncio
async def test_cache_invalidation_forces_reload() -> None:
    loader = AsyncMock(
        side_effect=[
            {
                "access_token": "old",
            },
            {
                "access_token": "new",
            },
        ]
    )

    cache = VaultSecretCache(ttl_seconds=60)

    first = await cache.get_or_load(
        path="tenant/path",
        loader=loader,
    )

    await cache.invalidate("tenant/path")

    second = await cache.get_or_load(
        path="tenant/path",
        loader=loader,
    )

    assert first["access_token"] == ("old")

    assert second["access_token"] == ("new")

    assert loader.await_count == 2
