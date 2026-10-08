from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest

from app.integrations.meta import (
    client as meta_client_module,
)
from app.integrations.meta import (
    media_client as media_client_module,
)
from app.integrations.meta.client import (
    MetaCloudAPIClient,
    MetaCloudAPIRetryableError,
)
from app.integrations.meta.media_client import (
    MetaMediaAPIClient,
    MetaMediaAPIRetryableError,
)


@pytest.mark.asyncio
async def test_meta_send_records_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observe = MagicMock()

    monkeypatch.setattr(
        meta_client_module.external_dependency_metrics,
        "observe",
        observe,
    )

    def handler(
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

    async with httpx.AsyncClient(transport=transport) as http_client:
        client = MetaCloudAPIClient(http_client)

        result = await client.send_text(
            graph_api_version="v23.0",
            phone_number_id="123456",
            recipient_phone="201000000000",
            body_text="hello",
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
async def test_meta_send_records_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observe = MagicMock()

    monkeypatch.setattr(
        meta_client_module.external_dependency_metrics,
        "observe",
        observe,
    )

    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        return httpx.Response(
            500,
            json={
                "error": {
                    "message": "temporary",
                }
            },
        )

    transport = httpx.MockTransport(handler)

    async with httpx.AsyncClient(transport=transport) as http_client:
        client = MetaCloudAPIClient(http_client)

        with pytest.raises(MetaCloudAPIRetryableError):
            await client.send_text(
                graph_api_version="v23.0",
                phone_number_id="123456",
                recipient_phone=("201000000000"),
                body_text="hello",
                access_token="secret-token",
            )

    kwargs = observe.call_args.kwargs

    assert kwargs["dependency"] == "meta"

    assert kwargs["operation"] == "send_text"

    assert kwargs["outcome"] == "failure"


@pytest.mark.asyncio
async def test_meta_media_records_metadata_and_download(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observe = MagicMock()

    monkeypatch.setattr(
        media_client_module.external_dependency_metrics,
        "observe",
        observe,
    )

    request_count = 0

    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        nonlocal request_count

        request_count += 1

        if request_count == 1:
            return httpx.Response(
                200,
                json={
                    "id": "media-123",
                    "url": ("https://lookaside.fbsbx.com/media-123"),
                    "mime_type": ("image/jpeg"),
                    "file_size": "3",
                },
            )

        return httpx.Response(
            200,
            content=b"abc",
            headers={
                "content-type": ("image/jpeg"),
            },
        )

    transport = httpx.MockTransport(handler)

    async with httpx.AsyncClient(transport=transport) as http_client:
        client = MetaMediaAPIClient(http_client)

        result = await client.download_media(
            graph_api_version="v23.0",
            provider_media_id=("media-123"),
            phone_number_id=("phone-123"),
            access_token=("secret-token"),
            max_size_bytes=1024,
        )

    assert result.data == b"abc"

    assert observe.call_count == 2

    first = observe.call_args_list[0].kwargs

    second = observe.call_args_list[1].kwargs

    assert first == {
        "dependency": "meta",
        "operation": ("media_metadata"),
        "outcome": "success",
        "duration_seconds": (first["duration_seconds"]),
    }

    assert second == {
        "dependency": "meta",
        "operation": ("media_download"),
        "outcome": "success",
        "duration_seconds": (second["duration_seconds"]),
    }

    assert first["duration_seconds"] >= 0

    assert second["duration_seconds"] >= 0


@pytest.mark.asyncio
async def test_meta_media_records_metadata_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observe = MagicMock()

    monkeypatch.setattr(
        media_client_module.external_dependency_metrics,
        "observe",
        observe,
    )

    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        return httpx.Response(
            500,
            json={
                "error": {
                    "message": "temporary",
                }
            },
        )

    transport = httpx.MockTransport(handler)

    async with httpx.AsyncClient(transport=transport) as http_client:
        client = MetaMediaAPIClient(http_client)

        with pytest.raises(MetaMediaAPIRetryableError):
            await client.download_media(
                graph_api_version="v23.0",
                provider_media_id=("media-123"),
                phone_number_id=("phone-123"),
                access_token=("secret-token"),
            )

    observe.assert_called_once()

    kwargs = observe.call_args.kwargs

    assert kwargs["dependency"] == "meta"

    assert kwargs["operation"] == "media_metadata"

    assert kwargs["outcome"] == "failure"
