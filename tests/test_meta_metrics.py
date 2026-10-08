from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest

from app.integrations.meta.client import (
    MetaCloudAPIClient,
    MetaCloudAPIRetryableError,
)
from app.integrations.meta.media_client import (
    MetaMediaAPIClient,
    MetaMediaAPIRetryableError,
)
from app.observability import (
    external_metrics as metrics_module,
)


@pytest.mark.asyncio
async def test_meta_send_text_records_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observe = MagicMock()

    monkeypatch.setattr(
        metrics_module.external_dependency_metrics,
        "observe",
        observe,
    )

    async def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "messages": [
                    {
                        "id": "wamid.123",
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handler)

    async with httpx.AsyncClient(
        transport=transport,
    ) as http_client:
        client = MetaCloudAPIClient(http_client)

        result = await client.send_text(
            graph_api_version="v23.0",
            phone_number_id="123",
            recipient_phone="201000000000",
            body_text="Hello",
            access_token="secret-token",
        )

    assert result.meta_message_id == "wamid.123"

    observe.assert_called_once()

    kwargs = observe.call_args.kwargs

    assert kwargs["dependency"] == "meta"

    assert kwargs["operation"] == "send_text"

    assert kwargs["outcome"] == "success"

    assert kwargs["duration_seconds"] >= 0


@pytest.mark.asyncio
async def test_meta_send_text_records_retryable_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observe = MagicMock()

    monkeypatch.setattr(
        metrics_module.external_dependency_metrics,
        "observe",
        observe,
    )

    async def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        return httpx.Response(
            503,
            json={"error": {"message": ("temporary")}},
        )

    transport = httpx.MockTransport(handler)

    async with httpx.AsyncClient(
        transport=transport,
    ) as http_client:
        client = MetaCloudAPIClient(http_client)

        with pytest.raises(MetaCloudAPIRetryableError):
            await client.send_text(
                graph_api_version="v23.0",
                phone_number_id="123",
                recipient_phone=("201000000000"),
                body_text="Hello",
                access_token="secret-token",
            )

    kwargs = observe.call_args.kwargs

    assert kwargs["dependency"] == "meta"

    assert kwargs["operation"] == "send_text"

    assert kwargs["outcome"] == "retryable_failure"


@pytest.mark.asyncio
async def test_meta_template_send_has_separate_operation_metric(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observe = MagicMock()

    monkeypatch.setattr(
        metrics_module.external_dependency_metrics,
        "observe",
        observe,
    )

    async def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "messages": [
                    {
                        "id": ("wamid.template"),
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handler)

    async with httpx.AsyncClient(
        transport=transport,
    ) as http_client:
        client = MetaCloudAPIClient(http_client)

        await client.send_template(
            graph_api_version="v23.0",
            phone_number_id="123",
            recipient_phone="201000000000",
            template_name="welcome",
            language="en_US",
            components=[],
            access_token="secret-token",
        )

    kwargs = observe.call_args.kwargs

    assert kwargs["operation"] == "send_template"

    assert kwargs["outcome"] == "success"


@pytest.mark.asyncio
async def test_meta_media_download_records_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observe = MagicMock()

    monkeypatch.setattr(
        metrics_module.external_dependency_metrics,
        "observe",
        observe,
    )

    async def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        if request.url.host == "graph.facebook.com":
            return httpx.Response(
                200,
                json={
                    "id": "media-123",
                    "url": ("https://lookaside.fbsbx.com/media-123"),
                    "mime_type": ("image/jpeg"),
                },
            )

        return httpx.Response(
            200,
            content=b"media-data",
            headers={
                "Content-Type": ("image/jpeg"),
            },
        )

    transport = httpx.MockTransport(handler)

    async with httpx.AsyncClient(
        transport=transport,
    ) as http_client:
        client = MetaMediaAPIClient(http_client)

        result = await client.download_media(
            graph_api_version="v23.0",
            provider_media_id=("media-123"),
            phone_number_id="123",
            access_token=("secret-token"),
            max_size_bytes=1024,
        )

    assert result.data == b"media-data"

    kwargs = observe.call_args.kwargs

    assert kwargs["dependency"] == "meta"

    assert kwargs["operation"] == "download_media"

    assert kwargs["outcome"] == "success"


@pytest.mark.asyncio
async def test_meta_media_retryable_failure_is_recorded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observe = MagicMock()

    monkeypatch.setattr(
        metrics_module.external_dependency_metrics,
        "observe",
        observe,
    )

    async def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        if request.url.host == "graph.facebook.com":
            return httpx.Response(
                200,
                json={
                    "id": "media-123",
                    "url": ("https://lookaside.fbsbx.com/media-123"),
                    "mime_type": ("image/jpeg"),
                },
            )

        return httpx.Response(404)

    transport = httpx.MockTransport(handler)

    async with httpx.AsyncClient(
        transport=transport,
    ) as http_client:
        client = MetaMediaAPIClient(http_client)

        with pytest.raises(MetaMediaAPIRetryableError):
            await client.download_media(
                graph_api_version="v23.0",
                provider_media_id=("media-123"),
                phone_number_id="123",
                access_token=("secret-token"),
                max_size_bytes=1024,
            )

    kwargs = observe.call_args.kwargs

    assert kwargs["operation"] == "download_media"

    assert kwargs["outcome"] == "retryable_failure"
