from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.models.raw_webhook_event import (
    RawWebhookEvent,
    RawWebhookProcessingStatus,
)
from app.db.session import (
    create_session_factory,
)
from app.repositories.meta_webhook import (
    MetaWebhookRepository,
)

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_concurrent_duplicate_ingress_only_one_insert_wins(
    integration_engine: AsyncEngine,
) -> None:
    session_factory = create_session_factory(integration_engine)

    provider_event_key = f"integration-test:{uuid4()}"

    start = asyncio.Event()
    ready = 0
    ready_lock = asyncio.Lock()
    both_ready = asyncio.Event()

    async def insert_once():
        nonlocal ready

        async with session_factory() as session:
            repository = MetaWebhookRepository(session)

            async with ready_lock:
                ready += 1

                if ready == 2:
                    both_ready.set()

            await both_ready.wait()
            await start.wait()

            async with session.begin():
                return await repository.insert_raw_event_if_new(
                    tenant_id=None,
                    provider_event_key=(provider_event_key),
                    event_type="messages",
                    payload_json={
                        "integration_test": True,
                    },
                    processing_status=(RawWebhookProcessingStatus.UNRESOLVED),
                    last_error=("INTEGRATION_TEST"),
                )

    first = asyncio.create_task(insert_once())
    second = asyncio.create_task(insert_once())

    await both_ready.wait()
    start.set()

    try:
        results = await asyncio.gather(
            first,
            second,
        )

        winners = [result for result in results if result is not None]

        duplicates = [result for result in results if result is None]

        assert len(winners) == 1
        assert len(duplicates) == 1

    finally:
        async with integration_engine.begin() as connection:
            await connection.execute(
                delete(RawWebhookEvent).where(
                    RawWebhookEvent.provider_event_key == provider_event_key
                )
            )
