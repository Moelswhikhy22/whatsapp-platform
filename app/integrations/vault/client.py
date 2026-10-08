from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

import hvac

from app.observability.external_metrics import (
    external_dependency_metrics,
)


@dataclass(frozen=True, slots=True)
class VaultClientConfig:
    url: str

    token: str | None = None
    token_file: str | None = None
    namespace: str | None = None

    verify: bool | str = True
    timeout_seconds: int = 10

    kv_mount_point: str = "secret"


class VaultClient:
    def __init__(
        self,
        config: VaultClientConfig,
    ) -> None:
        self._config = config

        token = self._resolve_token(config)

        self._client = hvac.Client(
            url=config.url,
            token=token,
            namespace=config.namespace,
            verify=config.verify,
            timeout=config.timeout_seconds,
        )

        self._lock = asyncio.Lock()

    async def is_authenticated(
        self,
    ) -> bool:
        started_at = perf_counter()

        try:
            async with self._lock:
                result = await asyncio.to_thread(
                    self._client.is_authenticated,
                )

        except Exception:
            self._observe(
                operation="authenticate",
                outcome="failure",
                started_at=started_at,
            )

            raise

        self._observe(
            operation="authenticate",
            outcome="success",
            started_at=started_at,
        )

        return result

    async def read_secret(
        self,
        *,
        path: str,
    ) -> dict[str, Any]:
        started_at = perf_counter()

        try:
            async with self._lock:
                response = await asyncio.to_thread(
                    (self._client.secrets.kv.v2.read_secret_version),
                    path=path,
                    mount_point=(self._config.kv_mount_point),
                )

        except Exception:
            self._observe(
                operation="read_secret",
                outcome="failure",
                started_at=started_at,
            )

            raise

        self._observe(
            operation="read_secret",
            outcome="success",
            started_at=started_at,
        )

        return dict(response["data"]["data"])

    async def write_secret(
        self,
        *,
        path: str,
        secret: dict[str, Any],
    ) -> None:
        started_at = perf_counter()

        try:
            async with self._lock:
                await asyncio.to_thread(
                    (self._client.secrets.kv.v2.create_or_update_secret),
                    path=path,
                    secret=secret,
                    mount_point=(self._config.kv_mount_point),
                )

        except Exception:
            self._observe(
                operation="write_secret",
                outcome="failure",
                started_at=started_at,
            )

            raise

        self._observe(
            operation="write_secret",
            outcome="success",
            started_at=started_at,
        )

    async def delete_latest_secret_version(
        self,
        *,
        path: str,
    ) -> None:
        started_at = perf_counter()

        try:
            async with self._lock:
                await asyncio.to_thread(
                    (self._client.secrets.kv.v2.delete_latest_version_of_secret),
                    path=path,
                    mount_point=(self._config.kv_mount_point),
                )

        except Exception:
            self._observe(
                operation=("delete_latest_secret_version"),
                outcome="failure",
                started_at=started_at,
            )

            raise

        self._observe(
            operation=("delete_latest_secret_version"),
            outcome="success",
            started_at=started_at,
        )

    async def close(
        self,
    ) -> None:
        async with self._lock:
            await asyncio.to_thread(
                self._client.session.close,
            )

    @staticmethod
    def _resolve_token(
        config: VaultClientConfig,
    ) -> str | None:
        direct_token = config.token.strip() if config.token else None

        token_file = config.token_file.strip() if config.token_file else None

        if direct_token is not None and token_file is not None:
            raise ValueError(("Vault token and token_file are mutually exclusive."))

        if token_file is None:
            return direct_token

        token = Path(token_file).read_text(encoding="utf-8").strip()

        if not token:
            raise ValueError("Vault token file is empty.")

        return token

    @staticmethod
    def _observe(
        *,
        operation: str,
        outcome: str,
        started_at: float,
    ) -> None:
        external_dependency_metrics.observe(
            dependency="vault",
            operation=operation,
            outcome=outcome,
            duration_seconds=max(
                perf_counter() - started_at,
                0.0,
            ),
        )
