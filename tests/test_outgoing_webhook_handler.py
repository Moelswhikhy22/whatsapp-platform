from __future__ import annotations

import json
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from app.integrations.rabbitmq.consumer import (
    PermanentMessageError,
)
from app.services.outgoing_webhook_delivery import (
    OutgoingWebhookEvent,
    OutgoingWebhookProcessResult,
    OutgoingWebhookRetryRequest,
)
from app.workers.outgoing_webhook_handler import (
    InvalidOutgoingWebhookJobError,
    OutgoingWebhookRabbitMQHandler,
    OutgoingWebhookRetryRequiredError,
)


def _event_body() -> tuple[
    bytes,
    UUID,
    UUID,
]:
    event_id = uuid4()
    tenant_id = uuid4()

    body = json.dumps(
        {
            "event_id": str(event_id),
            "tenant_id": str(tenant_id),
            "event_type": ("message.received"),
            "aggregate_type": ("message"),
            "aggregate_id": str(uuid4()),
            "occurred_at": ("2026-10-13T10:00:00+00:00"),
            "payload": {
                "message_id": str(uuid4()),
            },
        }
    ).encode()

    return (
        body,
        event_id,
        tenant_id,
    )


def _retry_body() -> tuple[
    bytes,
    UUID,
    UUID,
]:
    tenant_id = uuid4()
    delivery_id = uuid4()

    body = json.dumps(
        {
            "event_id": str(uuid4()),
            "tenant_id": str(tenant_id),
            "event_type": ("outgoing_webhook.retry_requested"),
            "aggregate_type": ("outgoing_webhook_delivery"),
            "aggregate_id": str(delivery_id),
            "occurred_at": ("2026-10-13T10:00:00+00:00"),
            "payload": {
                "delivery_id": str(delivery_id),
                "original_event_id": str(uuid4()),
            },
        }
    ).encode()

    return (
        body,
        tenant_id,
        delivery_id,
    )


def test_parse_valid_event() -> None:
    (
        body,
        event_id,
        tenant_id,
    ) = _event_body()

    event = OutgoingWebhookRabbitMQHandler._parse_event(body)

    assert event.event_id == event_id

    assert event.tenant_id == tenant_id

    assert event.event_type == "message.received"

    assert event.aggregate_type == "message"


def test_invalid_json_is_permanent() -> None:
    with pytest.raises(InvalidOutgoingWebhookJobError):
        (OutgoingWebhookRabbitMQHandler._parse_event(b"{invalid"))


def test_missing_event_id_is_permanent() -> None:
    body, _, _ = _event_body()

    payload = json.loads(body)

    del payload["event_id"]

    with pytest.raises(InvalidOutgoingWebhookJobError):
        (OutgoingWebhookRabbitMQHandler._parse_event(json.dumps(payload).encode()))


def test_invalid_tenant_uuid_is_permanent() -> None:
    body, _, _ = _event_body()

    payload = json.loads(body)

    payload["tenant_id"] = "not-a-uuid"

    with pytest.raises(InvalidOutgoingWebhookJobError):
        (OutgoingWebhookRabbitMQHandler._parse_event(json.dumps(payload).encode()))


@pytest.mark.asyncio
async def test_successful_processing_returns_normally(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body, _, _ = _event_body()

    handler = OutgoingWebhookRabbitMQHandler(
        session_factory=(AsyncMock()),
        service_factory=(AsyncMock()),
        max_attempts=5,
    )

    dispatch = AsyncMock(
        return_value=(
            OutgoingWebhookProcessResult(
                matched_subscriptions=1,
                attempted_deliveries=1,
                delivered=1,
                failed=0,
                retry_required=False,
            )
        )
    )

    monkeypatch.setattr(
        handler,
        "_dispatch",
        dispatch,
    )

    message = AsyncMock()

    message.body = body
    message.headers = {}

    await handler(message)

    dispatch.assert_awaited_once()

    call = dispatch.await_args.kwargs

    assert call["final_attempt"] is False


@pytest.mark.asyncio
async def test_retryable_result_requests_broker_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body, _, _ = _event_body()

    handler = OutgoingWebhookRabbitMQHandler(
        session_factory=(AsyncMock()),
        service_factory=(AsyncMock()),
        max_attempts=5,
    )

    dispatch = AsyncMock(
        return_value=(
            OutgoingWebhookProcessResult(
                matched_subscriptions=1,
                attempted_deliveries=1,
                delivered=0,
                failed=0,
                retry_required=True,
            )
        )
    )

    monkeypatch.setattr(
        handler,
        "_dispatch",
        dispatch,
    )

    message = AsyncMock()

    message.body = body
    message.headers = {
        "x-retry-count": 0,
    }

    with pytest.raises(OutgoingWebhookRetryRequiredError):
        await handler(message)


@pytest.mark.asyncio
async def test_fifth_attempt_is_marked_final(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body, _, _ = _event_body()

    handler = OutgoingWebhookRabbitMQHandler(
        session_factory=(AsyncMock()),
        service_factory=(AsyncMock()),
        max_attempts=5,
    )

    dispatch = AsyncMock(
        return_value=(
            OutgoingWebhookProcessResult(
                matched_subscriptions=1,
                attempted_deliveries=1,
                delivered=0,
                failed=1,
                retry_required=True,
            )
        )
    )

    monkeypatch.setattr(
        handler,
        "_dispatch",
        dispatch,
    )

    message = AsyncMock()

    message.body = body

    # Four prior retries means this
    # delivery is attempt number five.
    message.headers = {
        "x-retry-count": 4,
    }

    with pytest.raises(OutgoingWebhookRetryRequiredError):
        await handler(message)

    call = dispatch.await_args.kwargs

    assert call["final_attempt"] is True


@pytest.mark.asyncio
async def test_unsupported_but_valid_event_is_not_malformed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body, _, _ = _event_body()

    payload = json.loads(body)

    payload["event_type"] = "presence.changed"

    body = json.dumps(payload).encode()

    handler = OutgoingWebhookRabbitMQHandler(
        session_factory=(AsyncMock()),
        service_factory=(AsyncMock()),
    )

    dispatch = AsyncMock(
        return_value=(
            OutgoingWebhookProcessResult(
                matched_subscriptions=0,
                attempted_deliveries=0,
                delivered=0,
                failed=0,
                retry_required=False,
            )
        )
    )

    monkeypatch.setattr(
        handler,
        "_dispatch",
        dispatch,
    )

    message = AsyncMock()

    message.body = body
    message.headers = {}

    await handler(message)

    job = dispatch.await_args.kwargs["job"]

    assert isinstance(
        job,
        OutgoingWebhookEvent,
    )

    assert job.event_type == "presence.changed"


def test_invalid_max_attempts_is_rejected() -> None:
    with pytest.raises(ValueError):
        OutgoingWebhookRabbitMQHandler(
            session_factory=(AsyncMock()),
            service_factory=(AsyncMock()),
            max_attempts=0,
        )


def test_invalid_retry_header_is_treated_as_zero() -> None:
    handler = OutgoingWebhookRabbitMQHandler(
        session_factory=(AsyncMock()),
        service_factory=(AsyncMock()),
        max_attempts=5,
    )

    message = AsyncMock()

    message.headers = {"x-retry-count": ("invalid")}

    assert handler._retry_count(message) == 0


def test_invalid_job_error_is_permanent_message_error() -> None:
    error = InvalidOutgoingWebhookJobError("invalid")

    assert isinstance(
        error,
        PermanentMessageError,
    )


def test_parse_manual_retry_request() -> None:
    (
        body,
        tenant_id,
        delivery_id,
    ) = _retry_body()

    job = OutgoingWebhookRabbitMQHandler._parse_job(body)

    assert isinstance(
        job,
        OutgoingWebhookRetryRequest,
    )

    assert job.tenant_id == tenant_id

    assert job.delivery_id == delivery_id


def test_retry_request_requires_delivery_id() -> None:
    body, _, _ = _retry_body()

    envelope = json.loads(body)

    del envelope["payload"]["delivery_id"]

    with pytest.raises(InvalidOutgoingWebhookJobError):
        (OutgoingWebhookRabbitMQHandler._parse_job(json.dumps(envelope).encode()))


@pytest.mark.asyncio
async def test_manual_retry_is_dispatched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body, _, _ = _retry_body()

    handler = OutgoingWebhookRabbitMQHandler(
        session_factory=(AsyncMock()),
        service_factory=(AsyncMock()),
        max_attempts=5,
    )

    dispatch = AsyncMock(
        return_value=(
            OutgoingWebhookProcessResult(
                matched_subscriptions=1,
                attempted_deliveries=1,
                delivered=1,
                failed=0,
                retry_required=False,
            )
        )
    )

    monkeypatch.setattr(
        handler,
        "_dispatch",
        dispatch,
    )

    message = AsyncMock()

    message.body = body
    message.headers = {}

    await handler(message)

    job = dispatch.await_args.kwargs["job"]

    assert isinstance(
        job,
        OutgoingWebhookRetryRequest,
    )


@pytest.mark.asyncio
async def test_manual_retry_can_request_broker_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body, _, _ = _retry_body()

    handler = OutgoingWebhookRabbitMQHandler(
        session_factory=(AsyncMock()),
        service_factory=(AsyncMock()),
        max_attempts=5,
    )

    dispatch = AsyncMock(
        return_value=(
            OutgoingWebhookProcessResult(
                matched_subscriptions=1,
                attempted_deliveries=1,
                delivered=0,
                failed=0,
                retry_required=True,
            )
        )
    )

    monkeypatch.setattr(
        handler,
        "_dispatch",
        dispatch,
    )

    message = AsyncMock()

    message.body = body

    message.headers = {
        "x-retry-count": 0,
    }

    with pytest.raises(OutgoingWebhookRetryRequiredError):
        await handler(message)
