from __future__ import annotations

import time
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

import httpx

from app.integrations.webhooks.signing import (
    serialize_webhook_payload,
    sign_webhook_payload,
)
from app.integrations.webhooks.ssrf import (
    WebhookEndpointValidationError,
    WebhookEndpointValidator,
)


class WebhookDeliveryOutcome(StrEnum):
    DELIVERED = "delivered"
    RETRYABLE_FAILURE = "retryable_failure"
    PERMANENT_FAILURE = "permanent_failure"


@dataclass(
    frozen=True,
    slots=True,
)
class WebhookDeliveryResult:
    outcome: WebhookDeliveryOutcome
    http_status_code: int | None
    error_code: str | None


class WebhookHttpDeliveryClient:
    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient,
        endpoint_validator: (WebhookEndpointValidator),
    ) -> None:
        self._http_client = http_client
        self._endpoint_validator = endpoint_validator

    async def deliver(
        self,
        *,
        endpoint_url: str,
        event_id: UUID,
        event_type: str,
        payload: dict[str, object],
        signing_secret: str,
    ) -> WebhookDeliveryResult:
        try:
            normalized_url = await self._endpoint_validator.validate(endpoint_url)

        except WebhookEndpointValidationError:
            return WebhookDeliveryResult(
                outcome=(WebhookDeliveryOutcome.PERMANENT_FAILURE),
                http_status_code=None,
                error_code=("WEBHOOK_ENDPOINT_UNSAFE"),
            )

        timestamp = str(int(time.time()))

        body = serialize_webhook_payload(payload)

        signature = sign_webhook_payload(
            signing_secret=(signing_secret),
            timestamp=timestamp,
            body=body,
        )

        headers = {
            "Content-Type": ("application/json"),
            "User-Agent": ("whatsapp-platform-webhook/1.0"),
            "X-Webhook-Id": str(event_id),
            "X-Webhook-Event": (event_type),
            "X-Webhook-Timestamp": (timestamp),
            "X-Webhook-Signature": (signature),
        }

        try:
            response = await self._http_client.post(
                normalized_url,
                content=body,
                headers=headers,
                follow_redirects=False,
            )

        except (
            httpx.TimeoutException,
            httpx.TransportError,
        ):
            return WebhookDeliveryResult(
                outcome=(WebhookDeliveryOutcome.RETRYABLE_FAILURE),
                http_status_code=None,
                error_code=("WEBHOOK_NETWORK_FAILURE"),
            )

        status_code = response.status_code

        if 200 <= status_code < 300:
            return WebhookDeliveryResult(
                outcome=(WebhookDeliveryOutcome.DELIVERED),
                http_status_code=(status_code),
                error_code=None,
            )

        if (
            status_code
            in {
                408,
                425,
                429,
            }
            or status_code >= 500
        ):
            return WebhookDeliveryResult(
                outcome=(WebhookDeliveryOutcome.RETRYABLE_FAILURE),
                http_status_code=(status_code),
                error_code=("WEBHOOK_REMOTE_RETRYABLE"),
            )

        return WebhookDeliveryResult(
            outcome=(WebhookDeliveryOutcome.PERMANENT_FAILURE),
            http_status_code=status_code,
            error_code=("WEBHOOK_REMOTE_REJECTED"),
        )
