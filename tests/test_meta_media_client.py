from __future__ import annotations

import hashlib

import httpx
import pytest

from app.integrations.meta.media_client import (
    MetaMediaAPIClient,
    MetaMediaAPIRetryableError,
)


@pytest.mark.asyncio
async def test_download_media_validates_provider_metadata() -> None:
    data = b"media-content"

    sha256 = hashlib.sha256(data).hexdigest()

    async def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer secret-token"

        if request.url.host == "graph.facebook.com":
            assert request.url.path == "/v99.0/media-123"

            assert request.url.params["phone_number_id"] == "phone-123"

            return httpx.Response(
                200,
                json={
                    "messaging_product": ("whatsapp"),
                    "url": ("https://lookaside.fbsbx.com/media-123"),
                    "mime_type": ("image/jpeg"),
                    "sha256": sha256,
                    "file_size": str(len(data)),
                    "id": "media-123",
                },
            )

        return httpx.Response(
            200,
            content=data,
            headers={
                "content-type": ("image/jpeg"),
            },
        )

    transport = httpx.MockTransport(handler)

    async with httpx.AsyncClient(transport=transport) as http_client:
        client = MetaMediaAPIClient(http_client)

        result = await client.download_media(
            graph_api_version=("v99.0"),
            provider_media_id=("media-123"),
            phone_number_id=("phone-123"),
            access_token=("secret-token"),
        )

    assert result.data == data
    assert result.mime_type == ("image/jpeg")
    assert result.provider_sha256 == sha256
    assert result.provider_size_bytes == len(data)


@pytest.mark.asyncio
async def test_download_404_is_retryable() -> None:
    async def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        if request.url.host == "graph.facebook.com":
            return httpx.Response(
                200,
                json={
                    "url": ("https://lookaside.fbsbx.com/expired"),
                    "mime_type": ("image/jpeg"),
                    "file_size": "1",
                    "id": "media-123",
                },
            )

        return httpx.Response(404)

    transport = httpx.MockTransport(handler)

    async with httpx.AsyncClient(transport=transport) as http_client:
        client = MetaMediaAPIClient(http_client)

        with pytest.raises(MetaMediaAPIRetryableError):
            await client.download_media(
                graph_api_version=("v99.0"),
                provider_media_id=("media-123"),
                phone_number_id=("phone-123"),
                access_token=("secret-token"),
            )
