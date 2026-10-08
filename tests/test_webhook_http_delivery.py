from __future__ import annotations

import ipaddress
from uuid import uuid4

import httpx
import pytest

from app.integrations.webhooks.delivery import (
    WebhookDeliveryOutcome,
    WebhookHttpDeliveryClient,
)
from app.integrations.webhooks.ssrf import (
    WebhookEndpointValidator,
)


async def _public_resolver(
    host: str,
    port: int,
):
    return {ipaddress.ip_address("8.8.8.8")}


@pytest.mark.asyncio
async def test_webhook_delivery_sends_signed_request() -> None:
    event_id = uuid4()

    async def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        assert request.headers["X-Webhook-Id"] == str(event_id)

        assert request.headers["X-Webhook-Event"] == "message.received"

        assert request.headers["X-Webhook-Signature"].startswith("v1=")

        assert request.headers["X-Webhook-Timestamp"]

        return httpx.Response(204)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = WebhookHttpDeliveryClient(
            http_client=(http_client),
            endpoint_validator=(WebhookEndpointValidator(resolver=(_public_resolver))),
        )

        result = await client.deliver(
            endpoint_url=("https://example.com/hooks"),
            event_id=event_id,
            event_type=("message.received"),
            payload={
                "id": str(event_id),
                "type": ("message.received"),
                "data": {
                    "message_id": "123",
                },
            },
            signing_secret="s" * 32,
        )

    assert result.outcome is WebhookDeliveryOutcome.DELIVERED

    assert result.http_status_code == 204


@pytest.mark.asyncio
async def test_500_is_retryable() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(503))
    ) as http_client:
        client = WebhookHttpDeliveryClient(
            http_client=http_client,
            endpoint_validator=(WebhookEndpointValidator(resolver=(_public_resolver))),
        )

        result = await client.deliver(
            endpoint_url=("https://example.com/hooks"),
            event_id=uuid4(),
            event_type=("message.received"),
            payload={"data": {}},
            signing_secret="s" * 32,
        )

    assert result.outcome is WebhookDeliveryOutcome.RETRYABLE_FAILURE

    assert result.http_status_code == 503


@pytest.mark.asyncio
async def test_429_is_retryable() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(429))
    ) as http_client:
        client = WebhookHttpDeliveryClient(
            http_client=http_client,
            endpoint_validator=(WebhookEndpointValidator(resolver=(_public_resolver))),
        )

        result = await client.deliver(
            endpoint_url=("https://example.com/hooks"),
            event_id=uuid4(),
            event_type=("conversation.closed"),
            payload={"data": {}},
            signing_secret="s" * 32,
        )

    assert result.outcome is WebhookDeliveryOutcome.RETRYABLE_FAILURE


@pytest.mark.asyncio
async def test_400_is_permanent_failure() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(400))
    ) as http_client:
        client = WebhookHttpDeliveryClient(
            http_client=http_client,
            endpoint_validator=(WebhookEndpointValidator(resolver=(_public_resolver))),
        )

        result = await client.deliver(
            endpoint_url=("https://example.com/hooks"),
            event_id=uuid4(),
            event_type=("message.received"),
            payload={"data": {}},
            signing_secret="s" * 32,
        )

    assert result.outcome is WebhookDeliveryOutcome.PERMANENT_FAILURE


@pytest.mark.asyncio
async def test_private_address_is_rejected_before_http_request() -> None:
    request_count = 0

    async def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        nonlocal request_count
        request_count += 1

        return httpx.Response(200)

    async def private_resolver(
        host: str,
        port: int,
    ):
        return {ipaddress.ip_address("127.0.0.1")}

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = WebhookHttpDeliveryClient(
            http_client=http_client,
            endpoint_validator=(WebhookEndpointValidator(resolver=(private_resolver))),
        )

        result = await client.deliver(
            endpoint_url=("https://example.com/hooks"),
            event_id=uuid4(),
            event_type=("message.received"),
            payload={"data": {}},
            signing_secret="s" * 32,
        )

    assert request_count == 0

    assert result.outcome is WebhookDeliveryOutcome.PERMANENT_FAILURE

    assert result.error_code == "WEBHOOK_ENDPOINT_UNSAFE"
