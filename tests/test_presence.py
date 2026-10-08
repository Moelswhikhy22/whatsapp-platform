from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.presence import (
    PresenceStatus,
    PresenceStore,
)


NOW = datetime(
    2026,
    10,
    12,
    12,
    0,
    0,
    tzinfo=UTC,
)


def _store(
    redis: AsyncMock,
) -> PresenceStore:
    return PresenceStore(
        redis,
        session_ttl_seconds=60,
        clock=lambda: NOW,
    )


@pytest.mark.asyncio
async def test_heartbeat_registers_session() -> None:
    redis = AsyncMock()

    tenant_id = uuid4()
    employee_id = uuid4()

    store = _store(redis)

    await store.heartbeat(
        tenant_id=tenant_id,
        employee_id=employee_id,
        session_id="web-session-1",
    )

    sessions_key = f"tenant:{tenant_id}:presence:employee:{employee_id}:sessions"

    redis.zadd.assert_awaited_once_with(
        sessions_key,
        {
            "web-session-1": (NOW.timestamp() + 60),
        },
    )


@pytest.mark.asyncio
async def test_active_session_is_online() -> None:
    redis = AsyncMock()

    redis.zcard.return_value = 1
    redis.get.return_value = None

    store = _store(redis)

    result = await store.get_status(
        tenant_id=uuid4(),
        employee_id=uuid4(),
    )

    assert result is PresenceStatus.ONLINE


@pytest.mark.asyncio
async def test_no_active_session_is_offline() -> None:
    redis = AsyncMock()

    redis.zcard.return_value = 0

    store = _store(redis)

    result = await store.get_status(
        tenant_id=uuid4(),
        employee_id=uuid4(),
    )

    assert result is PresenceStatus.OFFLINE


@pytest.mark.asyncio
async def test_active_employee_can_be_busy() -> None:
    redis = AsyncMock()

    redis.zcard.return_value = 1
    redis.get.return_value = "busy"

    store = _store(redis)

    result = await store.get_status(
        tenant_id=uuid4(),
        employee_id=uuid4(),
    )

    assert result is PresenceStatus.BUSY


@pytest.mark.asyncio
async def test_active_employee_can_be_unavailable() -> None:
    redis = AsyncMock()

    redis.zcard.return_value = 1
    redis.get.return_value = "unavailable"

    store = _store(redis)

    result = await store.get_status(
        tenant_id=uuid4(),
        employee_id=uuid4(),
    )

    assert result is PresenceStatus.UNAVAILABLE


@pytest.mark.asyncio
async def test_end_session_removes_only_that_session() -> None:
    redis = AsyncMock()

    tenant_id = uuid4()
    employee_id = uuid4()

    store = _store(redis)

    await store.end_session(
        tenant_id=tenant_id,
        employee_id=employee_id,
        session_id="odoo-session-1",
    )

    redis.zrem.assert_awaited_once_with(
        (f"tenant:{tenant_id}:presence:employee:{employee_id}:sessions"),
        "odoo-session-1",
    )


@pytest.mark.asyncio
async def test_presence_keys_are_tenant_scoped() -> None:
    redis = AsyncMock()

    employee_id = uuid4()
    tenant_a = uuid4()
    tenant_b = uuid4()

    store = _store(redis)

    await store.heartbeat(
        tenant_id=tenant_a,
        employee_id=employee_id,
        session_id="session-a",
    )

    await store.heartbeat(
        tenant_id=tenant_b,
        employee_id=employee_id,
        session_id="session-b",
    )

    first_key = redis.zadd.await_args_list[0].args[0]

    second_key = redis.zadd.await_args_list[1].args[0]

    assert str(tenant_a) in first_key
    assert str(tenant_b) in second_key
    assert first_key != second_key


@pytest.mark.asyncio
async def test_last_seen_is_available_after_heartbeat() -> None:
    redis = AsyncMock()
    redis.get.return_value = NOW.isoformat()

    store = _store(redis)

    result = await store.get_last_seen(
        tenant_id=uuid4(),
        employee_id=uuid4(),
    )

    assert result == NOW


def test_presence_status_catalog() -> None:
    assert set(PresenceStatus) == {
        PresenceStatus.ONLINE,
        PresenceStatus.OFFLINE,
        PresenceStatus.BUSY,
        PresenceStatus.UNAVAILABLE,
    }
