from __future__ import annotations

import json

import httpx
import pytest

from app.integrations.meta.client import (
    MetaCloudAPIAmbiguousResponseError,
    MetaCloudAPIClient,
    MetaCloudAPIPermanentError,
    MetaCloudAPIRetryableError,
)


@pytest.mark.asyncio
async def test_send_text_returns_wamid() -> None:
    async def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer token-123"

        payload = json.loads(request.content)

        assert payload["messaging_product"] == "whatsapp"
        assert payload["to"] == "201000000000"
        assert payload["type"] == "text"
        assert payload["text"]["body"] == "Hello"

        return httpx.Response(
            200,
            json={
                "messaging_product": ("whatsapp"),
                "messages": [
                    {
                        "id": ("wamid.test-123"),
                    }
                ],
            },
        )

    transport = httpx.MockTransport(handler)

    async with httpx.AsyncClient(transport=transport) as http_client:
        client = MetaCloudAPIClient(http_client)

        result = await client.send_text(
            graph_api_version="v99.0",
            phone_number_id="123456",
            recipient_phone="201000000000",
            body_text="Hello",
            access_token="token-123",
        )

    assert result.meta_message_id == "wamid.test-123"


@pytest.mark.asyncio
async def test_http_500_is_retryable() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            500,
            json={
                "error": {
                    "code": 1,
                }
            },
        )
    )

    async with httpx.AsyncClient(transport=transport) as http_client:
        client = MetaCloudAPIClient(http_client)

        with pytest.raises(MetaCloudAPIRetryableError):
            await client.send_text(
                graph_api_version="v99.0",
                phone_number_id="123",
                recipient_phone="20100",
                body_text="Hello",
                access_token="token",
            )


@pytest.mark.asyncio
async def test_provider_rate_limit_code_is_retryable() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            400,
            json={
                "error": {
                    "code": 130429,
                }
            },
        )
    )

    async with httpx.AsyncClient(transport=transport) as http_client:
        client = MetaCloudAPIClient(http_client)

        with pytest.raises(MetaCloudAPIRetryableError):
            await client.send_text(
                graph_api_version="v99.0",
                phone_number_id="123",
                recipient_phone="20100",
                body_text="Hello",
                access_token="token",
            )


@pytest.mark.asyncio
async def test_reengagement_error_is_permanent() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            400,
            json={
                "error": {
                    "code": 131047,
                }
            },
        )
    )

    async with httpx.AsyncClient(transport=transport) as http_client:
        client = MetaCloudAPIClient(http_client)

        with pytest.raises(MetaCloudAPIPermanentError) as exc_info:
            await client.send_text(
                graph_api_version="v99.0",
                phone_number_id="123",
                recipient_phone="20100",
                body_text="Hello",
                access_token="token",
            )

    assert exc_info.value.meta_error_code == 131047


@pytest.mark.asyncio
async def test_success_without_wamid_is_ambiguous() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "messaging_product": ("whatsapp"),
                "messages": [],
            },
        )
    )

    async with httpx.AsyncClient(transport=transport) as http_client:
        client = MetaCloudAPIClient(http_client)

        with pytest.raises(MetaCloudAPIAmbiguousResponseError):
            await client.send_text(
                graph_api_version="v99.0",
                phone_number_id="123",
                recipient_phone="20100",
                body_text="Hello",
                access_token="token",
            )


@pytest.mark.asyncio
async def test_send_template_returns_wamid() -> None:
    async def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        payload = json.loads(request.content)

        assert payload["messaging_product"] == "whatsapp"
        assert payload["to"] == ("201000000000")
        assert payload["type"] == ("template")

        assert payload["template"] == {
            "name": "payment_reminder",
            "language": {
                "code": "en_US",
            },
            "components": [
                {
                    "type": "body",
                    "parameters": [
                        {
                            "type": "text",
                            "text": "Ahmed",
                        }
                    ],
                }
            ],
        }

        return httpx.Response(
            200,
            json={
                "messaging_product": ("whatsapp"),
                "messages": [
                    {
                        "id": ("wamid.template-123"),
                    }
                ],
            },
        )

    transport = httpx.MockTransport(handler)

    async with httpx.AsyncClient(transport=transport) as http_client:
        client = MetaCloudAPIClient(http_client)

        result = await client.send_template(
            graph_api_version="v99.0",
            phone_number_id="123456",
            recipient_phone=("201000000000"),
            template_name=("payment_reminder"),
            language="en_US",
            components=[
                {
                    "type": "body",
                    "parameters": [
                        {
                            "type": "text",
                            "text": "Ahmed",
                        }
                    ],
                }
            ],
            access_token="token-123",
        )

    assert result.meta_message_id == "wamid.template-123"
