from __future__ import annotations

from contextlib import (
    asynccontextmanager,
)
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import (
    AsyncMock,
    MagicMock,
)

import pytest
from prometheus_client import (
    CollectorRegistry,
)

from app.integrations.s3 import (
    client as s3_module,
)
from app.integrations.s3.client import (
    ManagedS3Client,
    S3ClientConfig,
)
from app.integrations.vault import (
    client as vault_module,
)
from app.integrations.vault.client import (
    VaultClient,
    VaultClientConfig,
)
from app.observability.external_metrics import (
    ExternalDependencyMetrics,
)


def test_external_metrics_record_operation() -> None:
    registry = CollectorRegistry()

    metrics = ExternalDependencyMetrics(
        registry=registry,
    )

    metrics.observe(
        dependency="vault",
        operation="read_secret",
        outcome="success",
        duration_seconds=0.125,
    )

    output = registry.get_sample_value(
        ("whatsapp_platform_external_dependency_operations_total"),
        {
            "dependency": "vault",
            "operation": "read_secret",
            "outcome": "success",
        },
    )

    assert output == 1.0

    duration_count = registry.get_sample_value(
        ("whatsapp_platform_external_dependency_operation_duration_seconds_count"),
        {
            "dependency": "vault",
            "operation": "read_secret",
        },
    )

    assert duration_count == 1.0


@pytest.mark.asyncio
async def test_vault_read_records_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observe = MagicMock()

    monkeypatch.setattr(
        vault_module.external_dependency_metrics,
        "observe",
        observe,
    )

    client = VaultClient(
        VaultClientConfig(
            url="http://vault:8200",
            token="test-token",
        )
    )

    read_secret = MagicMock(
        return_value={
            "data": {
                "data": {
                    "access_token": ("secret-value"),
                }
            }
        }
    )

    client._client.secrets.kv.v2.read_secret_version = (  # type: ignore[attr-defined]
        read_secret
    )

    result = await client.read_secret(
        path="tenant/example/meta",
    )

    assert result == {
        "access_token": "secret-value",
    }

    assert observe.call_args.kwargs["dependency"] == "vault"

    assert observe.call_args.kwargs["operation"] == "read_secret"

    assert observe.call_args.kwargs["outcome"] == "success"

    assert observe.call_args.kwargs["duration_seconds"] >= 0

    await client.close()


@pytest.mark.asyncio
async def test_vault_read_records_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observe = MagicMock()

    monkeypatch.setattr(
        vault_module.external_dependency_metrics,
        "observe",
        observe,
    )

    client = VaultClient(
        VaultClientConfig(
            url="http://vault:8200",
            token="test-token",
        )
    )

    read_secret = MagicMock(side_effect=RuntimeError("vault unavailable"))

    client._client.secrets.kv.v2.read_secret_version = (  # type: ignore[attr-defined]
        read_secret
    )

    with pytest.raises(
        RuntimeError,
    ):
        await client.read_secret(
            path="tenant/example/meta",
        )

    assert observe.call_args.kwargs["dependency"] == "vault"

    assert observe.call_args.kwargs["operation"] == "read_secret"

    assert observe.call_args.kwargs["outcome"] == "failure"

    await client.close()


@pytest.mark.asyncio
async def test_s3_upload_records_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observe = MagicMock()

    monkeypatch.setattr(
        s3_module.external_dependency_metrics,
        "observe",
        observe,
    )

    s3 = AsyncMock()

    @asynccontextmanager
    async def client_context():
        yield s3

    client = ManagedS3Client(S3ClientConfig())

    monkeypatch.setattr(
        client,
        "_client",
        client_context,
    )

    await client.upload_fileobj(
        fileobj=BytesIO(b"test-data"),
        bucket="test-bucket",
        key="tenant/media/object",
        content_type="image/jpeg",
    )

    s3.upload_fileobj.assert_awaited_once()

    assert observe.call_args.kwargs["dependency"] == "s3"

    assert observe.call_args.kwargs["operation"] == "upload"

    assert observe.call_args.kwargs["outcome"] == "success"

    assert observe.call_args.kwargs["duration_seconds"] >= 0


@pytest.mark.asyncio
async def test_s3_upload_records_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observe = MagicMock()

    monkeypatch.setattr(
        s3_module.external_dependency_metrics,
        "observe",
        observe,
    )

    s3 = AsyncMock()

    s3.upload_fileobj.side_effect = RuntimeError("s3 unavailable")

    @asynccontextmanager
    async def client_context():
        yield s3

    client = ManagedS3Client(S3ClientConfig())

    monkeypatch.setattr(
        client,
        "_client",
        client_context,
    )

    with pytest.raises(
        RuntimeError,
    ):
        await client.upload_fileobj(
            fileobj=BytesIO(b"test-data"),
            bucket="test-bucket",
            key="tenant/media/object",
        )

    assert observe.call_args.kwargs["dependency"] == "s3"

    assert observe.call_args.kwargs["operation"] == "upload"

    assert observe.call_args.kwargs["outcome"] == "failure"
