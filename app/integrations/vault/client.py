from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import hvac


@dataclass(frozen=True, slots=True)
class VaultClientConfig:
    url: str

    token: str | None = None
    namespace: str | None = None

    verify: bool | str = True
    timeout_seconds: int = 10

    kv_mount_point: str = "secret"


class VaultClient:
    def __init__(self, config: VaultClientConfig) -> None:
        self._config = config

        self._client = hvac.Client(
            url=config.url,
            token=config.token,
            namespace=config.namespace,
            verify=config.verify,
            timeout=config.timeout_seconds,
        )

        self._lock = asyncio.Lock()

    async def is_authenticated(self) -> bool:
        async with self._lock:
            return await asyncio.to_thread(
                self._client.is_authenticated,
            )

    async def read_secret(
        self,
        *,
        path: str,
    ) -> dict[str, Any]:
        async with self._lock:
            response = await asyncio.to_thread(
                self._client.secrets.kv.v2.read_secret_version,
                path=path,
                mount_point=self._config.kv_mount_point,
            )

        return dict(response["data"]["data"])

    async def write_secret(
        self,
        *,
        path: str,
        secret: dict[str, Any],
    ) -> None:
        async with self._lock:
            await asyncio.to_thread(
                self._client.secrets.kv.v2.create_or_update_secret,
                path=path,
                secret=secret,
                mount_point=self._config.kv_mount_point,
            )

    async def delete_latest_secret_version(
        self,
        *,
        path: str,
    ) -> None:
        async with self._lock:
            await asyncio.to_thread(
                self._client.secrets.kv.v2.delete_latest_version_of_secret,
                path=path,
                mount_point=self._config.kv_mount_point,
            )

    async def close(self) -> None:
        async with self._lock:
            await asyncio.to_thread(
                self._client.session.close,
            )
