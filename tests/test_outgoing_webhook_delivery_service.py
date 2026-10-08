from __future__ import annotations

from unittest.mock import (
    AsyncMock,
    MagicMock,
)
from uuid import uuid4

import pytest

from app.db.models.outgoing_webhook import (
    OutgoingWebhookDelivery,
    OutgoingWebhookDeliveryStatus,
    OutgoingWebhookSubscription,
)
from app.integrations.webhooks.delivery import (
    WebhookDeliveryOutcome,
    WebhookDeliveryResult,
    WebhookHttpDeliveryClient,
)
from app.integrations.webhooks.signing_secret import (
    VaultWebhookSigningSecretProvider,
    WebhookSigningSecret,
)
from app.repositories.outgoing_webhook import (
    OutgoingWebhookDeliveryRepository,
)
from app.services.outgoing_webhook_delivery import (
    OutgoingWebhookDeliveryService,
    OutgoingWebhookEvent,
)
from app.services.outgoing_webhook_delivery import (
    OutgoingWebhookDeliveryService,
    OutgoingWebhookEvent,
    OutgoingWebhookRetryRequest,
)


def _event():
    tenant_id = uuid4()

    return OutgoingWebhookEvent(
        event_id=uuid4(),
        tenant_id=tenant_id,
        event_type="message.received",
        aggregate_type="message",
        aggregate_id=str(uuid4()),
        occurred_at=("2026-10-13T10:00:00+00:00"),
        payload={"message_id": str(uuid4())},
    )


def _subscription(
    tenant_id,
):
    return OutgoingWebhookSubscription(
        id=uuid4(),
        tenant_id=tenant_id,
        name="ERP",
        endpoint_url=("https://example.com/hooks"),
        event_types_json=["message.received"],
        vault_secret_reference=("unused-in-service-test"),
        active=True,
    )


def _delivery(
    *,
    tenant_id,
    subscription_id,
    event_id,
):
    return OutgoingWebhookDelivery(
        id=uuid4(),
        tenant_id=tenant_id,
        subscription_id=(subscription_id),
        event_id=event_id,
        event_type="message.received",
        payload_json={},
        status=(OutgoingWebhookDeliveryStatus.PENDING),
        attempt_count=0,
    )


@pytest.mark.asyncio
async def test_successful_delivery_is_recorded() -> None:
    event = _event()

    subscription = _subscription(event.tenant_id)

    delivery = _delivery(
        tenant_id=event.tenant_id,
        subscription_id=(subscription.id),
        event_id=event.event_id,
    )

    repository = MagicMock(spec=(OutgoingWebhookDeliveryRepository))

    repository.tenant_id = event.tenant_id

    repository.list_active_subscriptions_for_event = AsyncMock(return_value=[subscription])

    repository.get_or_create_delivery = AsyncMock(return_value=delivery)

    repository.lock_delivery = AsyncMock(return_value=delivery)

    repository.flush = AsyncMock()

    secret_provider = AsyncMock(spec=(VaultWebhookSigningSecretProvider))

    secret_provider.get_secret.return_value = WebhookSigningSecret(value="s" * 32)

    delivery_client = AsyncMock(spec=WebhookHttpDeliveryClient)

    delivery_client.deliver.return_value = WebhookDeliveryResult(
        outcome=(WebhookDeliveryOutcome.DELIVERED),
        http_status_code=204,
        error_code=None,
    )

    service = OutgoingWebhookDeliveryService(
        repository=repository,
        signing_secret_provider=(secret_provider),
        delivery_client=(delivery_client),
    )

    result = await service.process_event(event=event)

    assert result.delivered == 1
    assert result.failed == 0
    assert not result.retry_required

    assert delivery.status is OutgoingWebhookDeliveryStatus.DELIVERED

    assert delivery.attempt_count == 1
    assert delivery.last_http_status_code == 204

    assert delivery.delivered_at is not None

    repository.add_attempt.assert_called_once()


@pytest.mark.asyncio
async def test_retryable_failure_remains_pending() -> None:
    event = _event()

    subscription = _subscription(event.tenant_id)

    delivery = _delivery(
        tenant_id=event.tenant_id,
        subscription_id=(subscription.id),
        event_id=event.event_id,
    )

    repository = MagicMock(spec=(OutgoingWebhookDeliveryRepository))

    repository.tenant_id = event.tenant_id

    repository.list_active_subscriptions_for_event = AsyncMock(return_value=[subscription])

    repository.get_or_create_delivery = AsyncMock(return_value=delivery)

    repository.lock_delivery = AsyncMock(return_value=delivery)

    repository.flush = AsyncMock()

    secret_provider = AsyncMock(spec=(VaultWebhookSigningSecretProvider))

    secret_provider.get_secret.return_value = WebhookSigningSecret(value="s" * 32)

    delivery_client = AsyncMock(spec=WebhookHttpDeliveryClient)

    delivery_client.deliver.return_value = WebhookDeliveryResult(
        outcome=(WebhookDeliveryOutcome.RETRYABLE_FAILURE),
        http_status_code=503,
        error_code=("WEBHOOK_REMOTE_RETRYABLE"),
    )

    service = OutgoingWebhookDeliveryService(
        repository=repository,
        signing_secret_provider=(secret_provider),
        delivery_client=(delivery_client),
    )

    result = await service.process_event(
        event=event,
        final_attempt=False,
    )

    assert result.retry_required

    assert delivery.status is OutgoingWebhookDeliveryStatus.PENDING

    assert delivery.attempt_count == 1
    assert delivery.delivered_at is None


@pytest.mark.asyncio
async def test_final_retryable_failure_becomes_failed() -> None:
    event = _event()

    subscription = _subscription(event.tenant_id)

    delivery = _delivery(
        tenant_id=event.tenant_id,
        subscription_id=(subscription.id),
        event_id=event.event_id,
    )

    repository = MagicMock(spec=(OutgoingWebhookDeliveryRepository))

    repository.tenant_id = event.tenant_id

    repository.list_active_subscriptions_for_event = AsyncMock(return_value=[subscription])

    repository.get_or_create_delivery = AsyncMock(return_value=delivery)

    repository.lock_delivery = AsyncMock(return_value=delivery)

    repository.flush = AsyncMock()

    secret_provider = AsyncMock(spec=(VaultWebhookSigningSecretProvider))

    secret_provider.get_secret.return_value = WebhookSigningSecret(value="s" * 32)

    delivery_client = AsyncMock(spec=WebhookHttpDeliveryClient)

    delivery_client.deliver.return_value = WebhookDeliveryResult(
        outcome=(WebhookDeliveryOutcome.RETRYABLE_FAILURE),
        http_status_code=503,
        error_code=("WEBHOOK_REMOTE_RETRYABLE"),
    )

    service = OutgoingWebhookDeliveryService(
        repository=repository,
        signing_secret_provider=(secret_provider),
        delivery_client=(delivery_client),
    )

    result = await service.process_event(
        event=event,
        final_attempt=True,
    )

    assert result.retry_required
    assert result.failed == 1

    assert delivery.status is OutgoingWebhookDeliveryStatus.FAILED


@pytest.mark.asyncio
async def test_permanent_failure_is_not_retried() -> None:
    event = _event()

    subscription = _subscription(event.tenant_id)

    delivery = _delivery(
        tenant_id=event.tenant_id,
        subscription_id=(subscription.id),
        event_id=event.event_id,
    )

    repository = MagicMock(spec=(OutgoingWebhookDeliveryRepository))

    repository.tenant_id = event.tenant_id

    repository.list_active_subscriptions_for_event = AsyncMock(return_value=[subscription])

    repository.get_or_create_delivery = AsyncMock(return_value=delivery)

    repository.lock_delivery = AsyncMock(return_value=delivery)

    repository.flush = AsyncMock()

    secret_provider = AsyncMock(spec=(VaultWebhookSigningSecretProvider))

    secret_provider.get_secret.return_value = WebhookSigningSecret(value="s" * 32)

    delivery_client = AsyncMock(spec=WebhookHttpDeliveryClient)

    delivery_client.deliver.return_value = WebhookDeliveryResult(
        outcome=(WebhookDeliveryOutcome.PERMANENT_FAILURE),
        http_status_code=400,
        error_code=("WEBHOOK_REMOTE_REJECTED"),
    )

    service = OutgoingWebhookDeliveryService(
        repository=repository,
        signing_secret_provider=(secret_provider),
        delivery_client=(delivery_client),
    )

    result = await service.process_event(event=event)

    assert not result.retry_required
    assert result.failed == 1

    assert delivery.status is OutgoingWebhookDeliveryStatus.FAILED


@pytest.mark.asyncio
async def test_already_delivered_event_is_idempotent() -> None:
    event = _event()

    subscription = _subscription(event.tenant_id)

    delivery = _delivery(
        tenant_id=event.tenant_id,
        subscription_id=(subscription.id),
        event_id=event.event_id,
    )

    delivery.status = OutgoingWebhookDeliveryStatus.DELIVERED

    repository = MagicMock(spec=(OutgoingWebhookDeliveryRepository))

    repository.tenant_id = event.tenant_id

    repository.list_active_subscriptions_for_event = AsyncMock(return_value=[subscription])

    repository.get_or_create_delivery = AsyncMock(return_value=delivery)

    repository.lock_delivery = AsyncMock(return_value=delivery)

    repository.flush = AsyncMock()

    secret_provider = AsyncMock(spec=(VaultWebhookSigningSecretProvider))

    delivery_client = AsyncMock(spec=WebhookHttpDeliveryClient)

    service = OutgoingWebhookDeliveryService(
        repository=repository,
        signing_secret_provider=(secret_provider),
        delivery_client=(delivery_client),
    )

    result = await service.process_event(event=event)

    assert result.attempted_deliveries == 0

    secret_provider.get_secret.assert_not_awaited()
    delivery_client.deliver.assert_not_awaited()


@pytest.mark.asyncio
async def test_non_webhook_domain_event_is_ignored() -> None:
    event = _event()

    unsupported = OutgoingWebhookEvent(
        event_id=event.event_id,
        tenant_id=event.tenant_id,
        event_type="presence.changed",
        aggregate_type="presence",
        aggregate_id=str(uuid4()),
        occurred_at=(event.occurred_at),
        payload={},
    )

    repository = MagicMock(spec=(OutgoingWebhookDeliveryRepository))

    repository.tenant_id = event.tenant_id

    secret_provider = AsyncMock(spec=(VaultWebhookSigningSecretProvider))

    delivery_client = AsyncMock(spec=WebhookHttpDeliveryClient)

    service = OutgoingWebhookDeliveryService(
        repository=repository,
        signing_secret_provider=(secret_provider),
        delivery_client=(delivery_client),
    )

    result = await service.process_event(event=unsupported)

    assert result.matched_subscriptions == 0

    assert not result.retry_required

    repository.list_active_subscriptions_for_event.assert_not_awaited()


@pytest.mark.asyncio
async def test_manual_retry_uses_original_event_identity() -> None:
    event = _event()

    subscription = _subscription(event.tenant_id)

    delivery = _delivery(
        tenant_id=event.tenant_id,
        subscription_id=(subscription.id),
        event_id=event.event_id,
    )

    delivery.attempt_count = 5

    original_payload = {
        "id": str(event.event_id),
        "type": ("message.received"),
        "occurred_at": (event.occurred_at),
        "resource": {
            "type": "message",
            "id": event.aggregate_id,
        },
        "data": {
            "message_id": "123",
        },
    }

    delivery.payload_json = original_payload

    repository = MagicMock(spec=(OutgoingWebhookDeliveryRepository))

    repository.tenant_id = event.tenant_id

    repository.lock_delivery = AsyncMock(return_value=delivery)

    repository.get_subscription = AsyncMock(return_value=subscription)

    repository.flush = AsyncMock()

    secret_provider = AsyncMock(spec=(VaultWebhookSigningSecretProvider))

    secret_provider.get_secret.return_value = WebhookSigningSecret(value="s" * 32)

    delivery_client = AsyncMock(spec=WebhookHttpDeliveryClient)

    delivery_client.deliver.return_value = WebhookDeliveryResult(
        outcome=(WebhookDeliveryOutcome.DELIVERED),
        http_status_code=204,
        error_code=None,
    )

    service = OutgoingWebhookDeliveryService(
        repository=repository,
        signing_secret_provider=(secret_provider),
        delivery_client=(delivery_client),
    )

    result = await service.process_retry_request(
        request=(
            OutgoingWebhookRetryRequest(
                tenant_id=(event.tenant_id),
                delivery_id=(delivery.id),
            )
        )
    )

    assert result.delivered == 1

    assert delivery.attempt_count == 6

    assert delivery.status is OutgoingWebhookDeliveryStatus.DELIVERED

    delivery_client.deliver.assert_awaited_once_with(
        endpoint_url=(subscription.endpoint_url),
        event_id=(event.event_id),
        event_type=("message.received"),
        payload=(original_payload),
        signing_secret=("s" * 32),
    )


@pytest.mark.asyncio
async def test_duplicate_manual_retry_command_does_not_send_again() -> None:
    event = _event()

    subscription = _subscription(event.tenant_id)

    delivery = _delivery(
        tenant_id=event.tenant_id,
        subscription_id=(subscription.id),
        event_id=event.event_id,
    )

    delivery.status = OutgoingWebhookDeliveryStatus.DELIVERED

    repository = MagicMock(spec=(OutgoingWebhookDeliveryRepository))

    repository.tenant_id = event.tenant_id

    repository.lock_delivery = AsyncMock(return_value=delivery)

    repository.flush = AsyncMock()

    secret_provider = AsyncMock(spec=(VaultWebhookSigningSecretProvider))

    delivery_client = AsyncMock(spec=WebhookHttpDeliveryClient)

    service = OutgoingWebhookDeliveryService(
        repository=repository,
        signing_secret_provider=(secret_provider),
        delivery_client=(delivery_client),
    )

    result = await service.process_retry_request(
        request=(
            OutgoingWebhookRetryRequest(
                tenant_id=(event.tenant_id),
                delivery_id=(delivery.id),
            )
        )
    )

    assert result.attempted_deliveries == 0

    secret_provider.get_secret.assert_not_awaited()

    delivery_client.deliver.assert_not_awaited()


@pytest.mark.asyncio
async def test_manual_retry_inactive_subscription_fails_permanently() -> None:
    event = _event()

    subscription = _subscription(event.tenant_id)

    subscription.active = False

    delivery = _delivery(
        tenant_id=event.tenant_id,
        subscription_id=(subscription.id),
        event_id=event.event_id,
    )

    repository = MagicMock(spec=(OutgoingWebhookDeliveryRepository))

    repository.tenant_id = event.tenant_id

    repository.lock_delivery = AsyncMock(return_value=delivery)

    repository.get_subscription = AsyncMock(return_value=subscription)

    repository.flush = AsyncMock()

    secret_provider = AsyncMock(spec=(VaultWebhookSigningSecretProvider))

    delivery_client = AsyncMock(spec=WebhookHttpDeliveryClient)

    service = OutgoingWebhookDeliveryService(
        repository=repository,
        signing_secret_provider=(secret_provider),
        delivery_client=(delivery_client),
    )

    result = await service.process_retry_request(
        request=(
            OutgoingWebhookRetryRequest(
                tenant_id=(event.tenant_id),
                delivery_id=(delivery.id),
            )
        )
    )

    assert result.failed == 1

    assert not result.retry_required

    assert delivery.status is OutgoingWebhookDeliveryStatus.FAILED

    assert delivery.last_error == "WEBHOOK_SUBSCRIPTION_INACTIVE"

    delivery_client.deliver.assert_not_awaited()
