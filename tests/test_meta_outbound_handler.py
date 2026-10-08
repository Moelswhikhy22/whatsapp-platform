from __future__ import annotations

import json
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.integrations.rabbitmq.consumer import (
    PermanentMessageError,
)
from app.services.meta_outbound import (
    MetaOutboundOutcome,
    MetaOutboundResult,
)
from app.workers.meta_outbound_handler import (
    InvalidMetaOutboundJobError,
    MetaOutboundRabbitMQHandler,
)


def _job_body() -> tuple[
    bytes,
    object,
    object,
]:
    tenant_id = uuid4()
    message_id = uuid4()

    return (
        json.dumps(
            {
                "event_id": str(uuid4()),
                "tenant_id": str(tenant_id),
                "event_type": ("meta.outbound.send"),
                "aggregate_type": ("message"),
                "aggregate_id": str(message_id),
                "payload": {
                    "message_id": str(message_id),
                },
            }
        ).encode(),
        tenant_id,
        message_id,
    )


def test_parse_valid_job() -> None:
    body, tenant_id, message_id = _job_body()

    job = MetaOutboundRabbitMQHandler._parse_job(body)

    assert job.tenant_id == tenant_id
    assert job.message_id == message_id


def test_rejects_wrong_event_type() -> None:
    body, _, _ = _job_body()

    payload = json.loads(body)

    payload["event_type"] = "meta.inbound.raw_event"

    with pytest.raises(InvalidMetaOutboundJobError):
        MetaOutboundRabbitMQHandler._parse_job(json.dumps(payload).encode())


def test_rejects_aggregate_mismatch() -> None:
    body, _, _ = _job_body()

    payload = json.loads(body)

    payload["aggregate_id"] = str(uuid4())

    with pytest.raises(InvalidMetaOutboundJobError):
        MetaOutboundRabbitMQHandler._parse_job(json.dumps(payload).encode())


@pytest.mark.asyncio
async def test_permanent_result_becomes_permanent_broker_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body, _, message_id = _job_body()

    handler = MetaOutboundRabbitMQHandler(
        session_factory=AsyncMock(),
        service_factory=AsyncMock(),
    )

    dispatch = AsyncMock(
        return_value=MetaOutboundResult(
            outcome=(MetaOutboundOutcome.PERMANENT_FAILURE),
            message_id=message_id,
            failure_code=("META_SEND_REJECTED"),
        )
    )

    monkeypatch.setattr(
        handler,
        "_dispatch",
        dispatch,
    )

    message = AsyncMock()
    message.body = body

    with pytest.raises(PermanentMessageError):
        await handler(message)


@pytest.mark.asyncio
async def test_sent_result_returns_normally(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body, _, message_id = _job_body()

    handler = MetaOutboundRabbitMQHandler(
        session_factory=AsyncMock(),
        service_factory=AsyncMock(),
    )

    dispatch = AsyncMock(
        return_value=MetaOutboundResult(
            outcome=(MetaOutboundOutcome.SENT),
            message_id=message_id,
            meta_message_id="wamid.123",
        )
    )

    monkeypatch.setattr(
        handler,
        "_dispatch",
        dispatch,
    )

    message = AsyncMock()
    message.body = body

    await handler(message)

    dispatch.assert_awaited_once()
