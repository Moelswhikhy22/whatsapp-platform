from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.auth.session_store import (
    RedisSessionStore,
    SessionRecord,
)


def _record() -> SessionRecord:
    return SessionRecord(
        status="pending_validation",
        access_token="access-token",
        id_token="id-token",
        refresh_token="refresh-token",
        token_type="Bearer",
        expires_in=300,
        refresh_expires_in=1800,
        scope="openid profile email",
        nonce="nonce-value",
    )


@pytest.mark.asyncio
async def test_create_session() -> None:
    redis = AsyncMock()

    store = RedisSessionStore(
        redis=redis,
        ttl_seconds=28_800,
    )

    await store.create(
        session_id="session-id",
        record=_record(),
    )

    redis.set.assert_awaited_once()

    args = redis.set.await_args

    assert args.args[0] == ("wp:session:session-id")

    assert args.kwargs["ex"] == 28_800


@pytest.mark.asyncio
async def test_get_session() -> None:
    redis = AsyncMock()

    record = _record()

    redis.get.return_value = record.to_json()

    store = RedisSessionStore(
        redis=redis,
        ttl_seconds=28_800,
    )

    result = await store.get(
        session_id="session-id",
    )

    assert result == record

    redis.get.assert_awaited_once_with("wp:session:session-id")


@pytest.mark.asyncio
async def test_get_missing_session() -> None:
    redis = AsyncMock()

    redis.get.return_value = None

    store = RedisSessionStore(
        redis=redis,
        ttl_seconds=28_800,
    )

    result = await store.get(
        session_id="missing-session",
    )

    assert result is None


@pytest.mark.asyncio
async def test_delete_session() -> None:
    redis = AsyncMock()

    store = RedisSessionStore(
        redis=redis,
        ttl_seconds=28_800,
    )

    await store.delete(
        session_id="session-id",
    )

    redis.delete.assert_awaited_once_with("wp:session:session-id")
