from __future__ import annotations

from uuid import uuid4

from app.redis_keys import RedisKeys


def test_rate_limit_key_is_tenant_scoped() -> None:
    tenant_a = uuid4()
    tenant_b = uuid4()

    key_a = RedisKeys.rate_limit(
        tenant_id=tenant_a,
        bucket="message-send",
        identity="user@example.com",
    )

    key_b = RedisKeys.rate_limit(
        tenant_id=tenant_b,
        bucket="message-send",
        identity="user@example.com",
    )

    assert key_a.startswith(f"tenant:{tenant_a}:rate_limit:")
    assert key_b.startswith(f"tenant:{tenant_b}:rate_limit:")
    assert key_a != key_b


def test_rate_limit_key_does_not_expose_identity() -> None:
    tenant_id = uuid4()

    key = RedisKeys.rate_limit(
        tenant_id=tenant_id,
        bucket="message-send",
        identity="sensitive-user-id",
    )

    assert "sensitive-user-id" not in key


def test_short_lock_key_is_tenant_scoped() -> None:
    tenant_id = uuid4()

    key = RedisKeys.short_lock(
        tenant_id=tenant_id,
        resource_type="conversation",
        resource_id="conversation-123",
    )

    assert key.startswith(f"tenant:{tenant_id}:lock:conversation:")

    assert "conversation-123" not in key
