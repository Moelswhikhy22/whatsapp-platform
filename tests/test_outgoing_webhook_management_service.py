from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import (
    AsyncMock,
    MagicMock,
)
from uuid import uuid4

import pytest

from app.authorization.context import (
    AuthorizationContext,
)
from app.authorization.errors import (
    AuthorizationDeniedError,
)
from app.authorization.roles import Role
from app.db.models.outgoing_webhook import (
    OutgoingWebhookDelivery,
    OutgoingWebhookDeliveryStatus,
)
from app.repositories.outbox_event import (
    OutboxEventRepository,
)
from app.repositories.outgoing_webhook import (
    OutgoingWebhookRepository,
)
from app.services.outgoing_webhook_management import (
    OUTGOING_WEBHOOK_RETRY_REQUESTED_EVENT,
    OutgoingWebhookDeliveryNotFoundError,
    OutgoingWebhookDeliveryRetryConflictError,
    OutgoingWebhookManagementService,
)


def _context(
    tenant_id,
    *,
    role=Role.TENANT_ADMIN,
) -> AuthorizationContext:
    return AuthorizationContext(
        actor_id="actor",
        role=role,
        tenant_id=tenant_id,
    )


def _delivery(
    *,
    tenant_id,
    status=(OutgoingWebhookDeliveryStatus.FAILED),
) -> OutgoingWebhookDelivery:
    return OutgoingWebhookDelivery(
        id=uuid4(),
        tenant_id=tenant_id,
        subscription_id=uuid4(),
        event_id=uuid4(),
        event_type=("message.received"),
        payload_json={"id": str(uuid4())},
        status=status,
        attempt_count=3,
        next_attempt_at=(datetime.now(UTC)),
        last_error=("WEBHOOK_REMOTE_RETRYABLE"),
    )


def _service(
    tenant_id,
):
    repository = MagicMock(spec=OutgoingWebhookRepository)

    repository.tenant_id = tenant_id

    repository.flush = AsyncMock()

    outbox = MagicMock(spec=OutboxEventRepository)

    outbox.tenant_id = tenant_id

    service = OutgoingWebhookManagementService(
        repository=repository,
        outbox_repository=outbox,
    )

    return (
        service,
        repository,
        outbox,
    )


@pytest.mark.asyncio
async def test_lists_tenant_deliveries() -> None:
    tenant_id = uuid4()

    (
        service,
        repository,
        _,
    ) = _service(tenant_id)

    delivery = _delivery(tenant_id=tenant_id)

    repository.list_deliveries = AsyncMock(return_value=[delivery])

    result = await service.list_deliveries(
        context=_context(tenant_id),
        subscription_id=None,
        status=(OutgoingWebhookDeliveryStatus.FAILED),
        limit=50,
        offset=0,
    )

    assert result == [delivery]

    repository.list_deliveries.assert_awaited_once_with(
        subscription_id=None,
        status=(OutgoingWebhookDeliveryStatus.FAILED),
        limit=50,
        offset=0,
    )


@pytest.mark.asyncio
async def test_employee_cannot_view_webhook_deliveries() -> None:
    tenant_id = uuid4()

    (
        service,
        repository,
        _,
    ) = _service(tenant_id)

    with pytest.raises(AuthorizationDeniedError):
        await service.list_deliveries(
            context=_context(
                tenant_id,
                role=Role.EMPLOYEE,
            ),
            subscription_id=None,
            status=None,
            limit=50,
            offset=0,
        )

    repository.list_deliveries.assert_not_called()


@pytest.mark.asyncio
async def test_attempts_require_existing_delivery() -> None:
    tenant_id = uuid4()

    (
        service,
        repository,
        _,
    ) = _service(tenant_id)

    repository.get_delivery = AsyncMock(return_value=None)

    with pytest.raises(OutgoingWebhookDeliveryNotFoundError):
        await service.list_attempts(
            context=_context(tenant_id),
            delivery_id=uuid4(),
        )


@pytest.mark.asyncio
async def test_failed_delivery_manual_retry_creates_outbox_command() -> None:
    tenant_id = uuid4()

    (
        service,
        repository,
        outbox,
    ) = _service(tenant_id)

    delivery = _delivery(tenant_id=tenant_id)

    original_attempt_count = delivery.attempt_count

    original_event_id = delivery.event_id

    repository.lock_delivery = AsyncMock(return_value=delivery)

    result = await service.retry_failed_delivery(
        context=_context(tenant_id),
        delivery_id=delivery.id,
    )

    assert result is delivery

    assert delivery.status is OutgoingWebhookDeliveryStatus.PENDING

    assert delivery.attempt_count == original_attempt_count

    assert delivery.event_id == original_event_id

    assert delivery.delivered_at is None

    assert delivery.next_attempt_at is not None

    outbox.add_event.assert_called_once_with(
        event_type=(OUTGOING_WEBHOOK_RETRY_REQUESTED_EVENT),
        aggregate_type=("outgoing_webhook_delivery"),
        aggregate_id=str(delivery.id),
        payload_json={
            "delivery_id": str(delivery.id),
            "original_event_id": str(delivery.event_id),
        },
    )

    repository.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_manual_retry_rejects_delivered_delivery() -> None:
    tenant_id = uuid4()

    (
        service,
        repository,
        outbox,
    ) = _service(tenant_id)

    delivery = _delivery(
        tenant_id=tenant_id,
        status=(OutgoingWebhookDeliveryStatus.DELIVERED),
    )

    repository.lock_delivery = AsyncMock(return_value=delivery)

    with pytest.raises(OutgoingWebhookDeliveryRetryConflictError):
        await service.retry_failed_delivery(
            context=_context(tenant_id),
            delivery_id=delivery.id,
        )

    outbox.add_event.assert_not_called()

    repository.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_manual_retry_missing_delivery_is_not_found() -> None:
    tenant_id = uuid4()

    (
        service,
        repository,
        outbox,
    ) = _service(tenant_id)

    repository.lock_delivery = AsyncMock(return_value=None)

    with pytest.raises(OutgoingWebhookDeliveryNotFoundError):
        await service.retry_failed_delivery(
            context=_context(tenant_id),
            delivery_id=uuid4(),
        )

    outbox.add_event.assert_not_called()
