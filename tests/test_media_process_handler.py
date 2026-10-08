from __future__ import annotations

import json
from unittest.mock import (
    AsyncMock,
)
from uuid import uuid4

from app.workers.media_process_handler import (
    MediaProcessRabbitMQHandler,
)


def test_media_process_job_parses_trusted_envelope() -> None:
    tenant_id = uuid4()
    message_id = uuid4()

    body = json.dumps(
        {
            "event_id": str(uuid4()),
            "tenant_id": str(tenant_id),
            "event_type": ("media.process"),
            "aggregate_type": ("message"),
            "aggregate_id": str(message_id),
            "payload": {
                "message_id": str(message_id),
                "provider_media_id": ("media-123"),
                "original_filename": ("invoice.pdf"),
                "webhook_mime_type": ("application/pdf"),
            },
        }
    ).encode("utf-8")

    handler = MediaProcessRabbitMQHandler(
        session_factory=(AsyncMock()),
        service_factory=(AsyncMock()),
    )

    job = handler._parse_job(body)

    assert job.tenant_id == (tenant_id)
    assert job.message_id == (message_id)
    assert job.provider_media_id == "media-123"
