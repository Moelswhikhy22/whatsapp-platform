from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from redis.asyncio import Redis


class PresenceStatus(StrEnum):
    ONLINE = "online"
    OFFLINE = "offline"
    BUSY = "busy"
    UNAVAILABLE = "unavailable"


class PresenceStore:
    def __init__(
        self,
        redis: Redis,
        *,
        session_ttl_seconds: int = 60,
        last_seen_ttl_seconds: int = 604800,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if session_ttl_seconds <= 0:
            raise ValueError("session_ttl_seconds must be greater than zero")

        if last_seen_ttl_seconds <= 0:
            raise ValueError("last_seen_ttl_seconds must be greater than zero")

        self._redis = redis
        self._session_ttl_seconds = session_ttl_seconds
        self._last_seen_ttl_seconds = last_seen_ttl_seconds
        self._clock = clock or (lambda: datetime.now(UTC))

    async def heartbeat(
        self,
        *,
        tenant_id: UUID,
        employee_id: UUID,
        session_id: str,
    ) -> None:
        if not session_id:
            raise ValueError("session_id must not be empty")

        now = self._clock()
        expires_at = now.timestamp() + self._session_ttl_seconds

        sessions_key = self._sessions_key(
            tenant_id,
            employee_id,
        )

        await self._redis.zadd(
            sessions_key,
            {
                session_id: expires_at,
            },
        )

        await self._redis.expire(
            sessions_key,
            self._session_ttl_seconds * 2,
        )

        await self._redis.set(
            self._last_seen_key(
                tenant_id,
                employee_id,
            ),
            now.isoformat(),
            ex=self._last_seen_ttl_seconds,
        )

        # Keep BUSY / UNAVAILABLE alive while sessions
        # continue sending heartbeats.
        await self._redis.expire(
            self._status_key(
                tenant_id,
                employee_id,
            ),
            self._session_ttl_seconds * 2,
        )

    async def set_status(
        self,
        *,
        tenant_id: UUID,
        employee_id: UUID,
        status: PresenceStatus,
    ) -> None:
        status_key = self._status_key(
            tenant_id,
            employee_id,
        )

        if status is PresenceStatus.OFFLINE:
            await self.mark_offline(
                tenant_id=tenant_id,
                employee_id=employee_id,
            )
            return

        if status is PresenceStatus.ONLINE:
            await self._redis.delete(status_key)
            return

        await self._redis.set(
            status_key,
            status.value,
            ex=self._session_ttl_seconds * 2,
        )

    async def end_session(
        self,
        *,
        tenant_id: UUID,
        employee_id: UUID,
        session_id: str,
    ) -> None:
        await self._redis.zrem(
            self._sessions_key(
                tenant_id,
                employee_id,
            ),
            session_id,
        )

    async def mark_offline(
        self,
        *,
        tenant_id: UUID,
        employee_id: UUID,
    ) -> None:
        await self._redis.delete(
            self._sessions_key(
                tenant_id,
                employee_id,
            ),
            self._status_key(
                tenant_id,
                employee_id,
            ),
        )

    async def get_status(
        self,
        *,
        tenant_id: UUID,
        employee_id: UUID,
    ) -> PresenceStatus:
        now = self._clock()

        sessions_key = self._sessions_key(
            tenant_id,
            employee_id,
        )

        await self._redis.zremrangebyscore(
            sessions_key,
            "-inf",
            now.timestamp(),
        )

        active_sessions = await self._redis.zcard(
            sessions_key,
        )

        if active_sessions <= 0:
            await self._redis.delete(
                self._status_key(
                    tenant_id,
                    employee_id,
                )
            )

            return PresenceStatus.OFFLINE

        raw_status = await self._redis.get(
            self._status_key(
                tenant_id,
                employee_id,
            )
        )

        if raw_status is None:
            return PresenceStatus.ONLINE

        if isinstance(raw_status, bytes):
            raw_status = raw_status.decode()

        try:
            status = PresenceStatus(raw_status)
        except ValueError:
            return PresenceStatus.ONLINE

        if status in {
            PresenceStatus.BUSY,
            PresenceStatus.UNAVAILABLE,
        }:
            return status

        return PresenceStatus.ONLINE

    async def get_last_seen(
        self,
        *,
        tenant_id: UUID,
        employee_id: UUID,
    ) -> datetime | None:
        raw_value = await self._redis.get(
            self._last_seen_key(
                tenant_id,
                employee_id,
            )
        )

        if raw_value is None:
            return None

        if isinstance(raw_value, bytes):
            raw_value = raw_value.decode()

        return datetime.fromisoformat(raw_value)

    @staticmethod
    def _base_key(
        tenant_id: UUID,
        employee_id: UUID,
    ) -> str:
        return f"tenant:{tenant_id}:presence:employee:{employee_id}"

    @classmethod
    def _sessions_key(
        cls,
        tenant_id: UUID,
        employee_id: UUID,
    ) -> str:
        return f"{cls._base_key(tenant_id, employee_id)}:sessions"

    @classmethod
    def _status_key(
        cls,
        tenant_id: UUID,
        employee_id: UUID,
    ) -> str:
        return f"{cls._base_key(tenant_id, employee_id)}:status"

    @classmethod
    def _last_seen_key(
        cls,
        tenant_id: UUID,
        employee_id: UUID,
    ) -> str:
        return f"{cls._base_key(tenant_id, employee_id)}:last_seen"
