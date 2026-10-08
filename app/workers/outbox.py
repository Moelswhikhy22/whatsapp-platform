from __future__ import annotations

import asyncio
import logging
import signal

from app.core.config import get_settings
from app.db.session import (
    create_database_engine,
    create_session_factory,
)
from app.integrations.rabbitmq.client import (
    RabbitMQClient,
)
from app.integrations.rabbitmq.outbox_publisher import (
    RabbitMQOutboxPublisher,
)
from app.integrations.rabbitmq.topology import (
    declare_topology,
)
from app.repositories.outbox_publisher import (
    OutboxPublisherRepository,
)
from app.services.outbox_publisher import (
    OutboxPublishOutcome,
    OutboxPublisherService,
)

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 1.0
BATCH_SIZE = 100


async def run_outbox_worker() -> None:
    settings = get_settings()

    engine = create_database_engine(
        settings.database_url,
    )

    session_factory = create_session_factory(
        engine,
    )

    rabbitmq = RabbitMQClient(
        settings.rabbitmq_url,
    )

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def request_shutdown() -> None:
        stop_event.set()

    for sig in (
        signal.SIGINT,
        signal.SIGTERM,
    ):
        try:
            loop.add_signal_handler(
                sig,
                request_shutdown,
            )
        except NotImplementedError:
            signal.signal(
                sig,
                lambda *_: loop.call_soon_threadsafe(request_shutdown),
            )

    await rabbitmq.connect()

    channel = await rabbitmq.open_channel()

    exchange = await declare_topology(
        channel,
    )

    broker = RabbitMQOutboxPublisher(
        exchange,
    )

    logger.info("Outbox publisher worker started.")

    try:
        while not stop_event.is_set():
            processed_count = 0

            for _ in range(BATCH_SIZE):
                async with session_factory() as session:
                    async with session.begin():
                        repository = OutboxPublisherRepository(
                            session,
                        )

                        service = OutboxPublisherService(
                            repository=repository,
                            broker=broker,
                        )

                        result = await service.publish_next()

                if result.outcome is OutboxPublishOutcome.IDLE:
                    break

                processed_count += 1

            if processed_count > 0:
                continue

            try:
                await asyncio.wait_for(
                    stop_event.wait(),
                    timeout=POLL_INTERVAL_SECONDS,
                )
            except TimeoutError:
                pass
    finally:
        logger.info("Outbox publisher worker shutting down.")

        if not channel.is_closed:
            await channel.close()

        await rabbitmq.close()
        await engine.dispose()


def main() -> None:
    asyncio.run(run_outbox_worker())


if __name__ == "__main__":
    main()
