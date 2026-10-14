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

    assert kwargs["outcome"] == "retryable_failure"


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

    assert observe.call_count == 3

    metadata = observe.call_args_list[0].kwargs
    download = observe.call_args_list[1].kwargs
    high_level = observe.call_args_list[2].kwargs

    assert metadata == {
        "dependency": "meta",
        "operation": "media_metadata",
        "outcome": "success",
        "duration_seconds": metadata["duration_seconds"],
    }

    assert download == {
        "dependency": "meta",
        "operation": "media_download",
        "outcome": "success",
        "duration_seconds": download["duration_seconds"],
    }

    assert high_level == {
        "dependency": "meta",
        "operation": "download_media",
        "outcome": "success",
        "duration_seconds": high_level["duration_seconds"],
    }

    assert metadata["duration_seconds"] >= 0
    assert download["duration_seconds"] >= 0
    assert high_level["duration_seconds"] >= 0


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

    assert observe.call_count == 2

    metadata = observe.call_args_list[0].kwargs
    high_level = observe.call_args_list[1].kwargs

    assert metadata["dependency"] == "meta"
    assert metadata["operation"] == "media_metadata"
    assert metadata["outcome"] == "failure"

    assert high_level["dependency"] == "meta"
    assert high_level["operation"] == "download_media"
    assert high_level["outcome"] == "retryable_failure"
