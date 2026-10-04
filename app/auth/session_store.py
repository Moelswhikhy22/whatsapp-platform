from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Literal, cast

from redis.asyncio import Redis
from redis.exceptions import RedisError

SESSION_KEY_PREFIX = "wp:session:"

SessionStatus = Literal[
    "pending_validation",
    "authenticated",
]


class SessionStorageError(RuntimeError):
    """Raised when Redis session operations fail."""


@dataclass(
    frozen=True,
    slots=True,
)
class SessionRecord:
    status: SessionStatus
    access_token: str
    id_token: str
    refresh_token: str | None
    token_type: str
    expires_in: int
    refresh_expires_in: int | None
    scope: str | None
    nonce: str

    def to_json(self) -> str:
        return json.dumps(
            asdict(self),
            separators=(",", ":"),
        )

    @classmethod
    def from_json(
        cls,
        value: str,
    ) -> SessionRecord:
        raw_payload: object = json.loads(value)

        if not isinstance(
            raw_payload,
            dict,
        ):
            raise ValueError("Invalid session payload.")

        payload: dict[str, object] = {
            key: item for key, item in raw_payload.items() if isinstance(key, str)
        }

        status_value = _required_str(
            payload,
            "status",
        )

        if status_value not in {
            "pending_validation",
            "authenticated",
        }:
            raise ValueError("Invalid session status.")

        return cls(
            status=cast(
                SessionStatus,
                status_value,
            ),
            access_token=_required_str(
                payload,
                "access_token",
            ),
            id_token=_required_str(
                payload,
                "id_token",
            ),
            refresh_token=_optional_str(
                payload,
                "refresh_token",
            ),
            token_type=_required_str(
                payload,
                "token_type",
            ),
            expires_in=_required_int(
                payload,
                "expires_in",
            ),
            refresh_expires_in=_optional_int(
                payload,
                "refresh_expires_in",
            ),
            scope=_optional_str(
                payload,
                "scope",
            ),
            nonce=_required_str(
                payload,
                "nonce",
            ),
        )


def _required_str(
    payload: dict[str, object],
    name: str,
) -> str:
    value = payload.get(name)

    if not isinstance(value, str) or not value:
        raise ValueError(f"Invalid session field: {name}.")

    return value


def _optional_str(
    payload: dict[str, object],
    name: str,
) -> str | None:
    value = payload.get(name)

    if value is None:
        return None

    if not isinstance(value, str):
        raise ValueError(f"Invalid session field: {name}.")

    return value


def _required_int(
    payload: dict[str, object],
    name: str,
) -> int:
    value = payload.get(name)

    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"Invalid session field: {name}.")

    return value


def _optional_int(
    payload: dict[str, object],
    name: str,
) -> int | None:
    value = payload.get(name)

    if value is None:
        return None

    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"Invalid session field: {name}.")

    return value


class RedisSessionStore:
    def __init__(
        self,
        *,
        redis: Redis,
        ttl_seconds: int,
    ) -> None:
        self._redis = redis
        self._ttl_seconds = ttl_seconds

    @staticmethod
    def _key(
        session_id: str,
    ) -> str:
        return f"{SESSION_KEY_PREFIX}{session_id}"

    async def create(
        self,
        *,
        session_id: str,
        record: SessionRecord,
    ) -> None:
        try:
            await self._redis.set(
                self._key(session_id),
                record.to_json(),
                ex=self._ttl_seconds,
            )
        except RedisError as exc:
            raise SessionStorageError("Could not persist session.") from exc

    async def get(
        self,
        *,
        session_id: str,
    ) -> SessionRecord | None:
        try:
            value = await self._redis.get(self._key(session_id))
        except RedisError as exc:
            raise SessionStorageError("Could not read session.") from exc

        if value is None:
            return None

        if isinstance(value, bytes):
            value = value.decode("utf-8")

        return SessionRecord.from_json(value)

    async def delete(
        self,
        *,
        session_id: str,
    ) -> None:
        try:
            await self._redis.delete(self._key(session_id))
        except RedisError as exc:
            raise SessionStorageError("Could not delete session.") from exc
