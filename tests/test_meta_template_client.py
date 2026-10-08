from __future__ import annotations

import json

import httpx
import pytest

from app.integrations.meta.template_client import (
    MetaTemplateAPIClient,
    MetaTemplateAPIPermanentError,
    MetaTemplateAPIRetryableError,
)


@pytest.mark.asyncio
async def test_submit_template_returns_provider_result() -> None:
    async def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        assert request.url.path == ("/v99.0/123456/message_templates")

        assert request.headers["Authorization"] == "Bearer secret-token"

        payload = json.loads(request.content)

        assert payload == {
            "name": "payment_reminder",
            "language": "en_US",
            "category": "UTILITY",
            "components": [
                {
                    "type": "BODY",
                    "text": "Hello {{1}}",
                }
            ],
        }

        return httpx.Response(
            200,
            json={
                "id": "987654321",
                "status": "PENDING",
            },
        )

    transport = httpx.MockTransport(handler)

    async with httpx.AsyncClient(transport=transport) as http_client:
        client = MetaTemplateAPIClient(http_client)

        result = await client.submit_template(
            graph_api_version="v99.0",
            waba_id="123456",
            name="payment_reminder",
            language="en_US",
            category="UTILITY",
            components=[
                {
                    "type": "BODY",
                    "text": "Hello {{1}}",
                }
            ],
            access_token="secret-token",
        )

    assert result.provider_template_id == "987654321"
    assert result.provider_status == "PENDING"


@pytest.mark.asyncio
async def test_meta_validation_error_is_permanent() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            400,
            json={
                "error": {
                    "code": 100,
                    "message": "Invalid template",
                }
            },
        )
    )

    async with httpx.AsyncClient(transport=transport) as http_client:
        client = MetaTemplateAPIClient(http_client)

        with pytest.raises(MetaTemplateAPIPermanentError):
            await client.submit_template(
                graph_api_version="v99.0",
                waba_id="123",
                name="test",
                language="en_US",
                category="UTILITY",
                components=[
                    {
                        "type": "BODY",
                    }
                ],
                access_token="token",
            )


@pytest.mark.asyncio
async def test_meta_500_is_retryable() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            500,
            json={},
        )
    )

    async with httpx.AsyncClient(transport=transport) as http_client:
        client = MetaTemplateAPIClient(http_client)

        with pytest.raises(MetaTemplateAPIRetryableError):
            await client.submit_template(
                graph_api_version="v99.0",
                waba_id="123",
                name="test",
                language="en_US",
                category="UTILITY",
                components=[
                    {
                        "type": "BODY",
                    }
                ],
                access_token="token",
            )


@pytest.mark.asyncio
async def test_meta_transient_graph_error_is_retryable() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            400,
            json={
                "error": {
                    "code": 1,
                    "is_transient": True,
                }
            },
        )
    )

    async with httpx.AsyncClient(transport=transport) as http_client:
        client = MetaTemplateAPIClient(http_client)

        with pytest.raises(MetaTemplateAPIRetryableError):
            await client.submit_template(
                graph_api_version="v99.0",
                waba_id="123",
                name="test",
                language="en_US",
                category="UTILITY",
                components=[
                    {
                        "type": "BODY",
                    }
                ],
                access_token="token",
            )


@pytest.mark.asyncio
async def test_fetch_templates_follows_pagination() -> None:
    calls = 0

    async def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        nonlocal calls
        calls += 1

        if calls == 1:
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "1",
                            "name": "first",
                            "language": "en_US",
                            "category": "UTILITY",
                            "status": "APPROVED",
                            "components": [],
                        }
                    ],
                    "paging": {
                        "next": (
                            "https://graph.facebook.com/v99.0/123/message_templates?after=cursor-1"
                        )
                    },
                },
            )

        assert request.url.params["after"] == "cursor-1"

        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "2",
                        "name": "second",
                        "language": "ar",
                        "category": "MARKETING",
                        "status": "PENDING",
                        "components": [],
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handler)

    async with httpx.AsyncClient(transport=transport) as http_client:
        client = MetaTemplateAPIClient(http_client)

        result = await client.fetch_templates(
            graph_api_version="v99.0",
            waba_id="123",
            access_token="token",
        )

    assert calls == 2
    assert len(result) == 2
    assert result[0].name == "first"
    assert result[1].name == "second"
