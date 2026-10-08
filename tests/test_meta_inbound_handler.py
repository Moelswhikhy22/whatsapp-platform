from __future__ import annotations

import json
from uuid import uuid4

import pytest

from app.workers.meta_inbound_handler import (
    InvalidMetaInboundJobError,
    MetaInboundRabbitMQHandler,
)


def test_parse_valid_outbox_job() -> None:
    raw_event_id = uuid4()

    body = json.dumps(
        {
            "event_type": ("meta.inbound.raw_event"),
            "payload": {
                "raw_event_id": str(raw_event_id),
            },
        }
    ).encode()

    result = MetaInboundRabbitMQHandler._parse_job(body)

    assert result == raw_event_id


@pytest.mark.parametrize(
    "body",
    [
        b"not-json",
        b"[]",
        json.dumps(
            {
                "event_type": ("message.received"),
                "payload": {},
            }
        ).encode(),
        json.dumps(
            {
                "event_type": ("meta.inbound.raw_event"),
                "payload": {},
            }
        ).encode(),
        json.dumps(
            {
                "event_type": ("meta.inbound.raw_event"),
                "payload": {
                    "raw_event_id": ("not-a-uuid"),
                },
            }
        ).encode(),
    ],
)
def test_invalid_job_is_permanent_failure(
    body: bytes,
) -> None:
    with pytest.raises(InvalidMetaInboundJobError):
        (MetaInboundRabbitMQHandler._parse_job(body))
