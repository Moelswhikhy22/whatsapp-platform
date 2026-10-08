from __future__ import annotations

import asyncio
import signal
from uuid import UUID

from aio_pika import ExchangeType
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from app.core.config import get_settings
from app.core.redis import (
    create_redis_client,
)
from app.db.session import (
    create_database_engine,
    create_session_factory,
)
from app.integrations.rabbitmq.client import (
    RabbitMQClient,
)
from app.integrations.rabbitmq.consumer import (
    ReliableConsumer,
)
from app.integrations.rabbitmq.topology import (
    DEAD_LETTER_EXCHANGE_NAME,
    META_INBOUND_QUEUE,
    RETRY_EXCHANGE_NAME,
    declare_topology,
)
from app.presence import PresenceStore
from app.services.incoming_message import (
    IncomingMessageProcessor,
)
from app.services.meta_inbound_dispatcher import (
    MetaStatusProcessor,
)
from app.workers.meta_inbound_dependencies import (
    build_meta_inbound_processors,
)
from app.workers.meta_inbound_handler import (
    MetaInboundRabbitMQHandler,
)


PREFETCH_COUNT = 20


async def run_worker() -> None:
    settings = get_settings()

    database_engine = create_database_engine(settings.database_url)

    session_factory = create_session_factory(database_engine)

    redis = create_redis_client(settings.redis_url)

    presence_store = PresenceStore(redis)

    rabbitmq = RabbitMQClient(settings.rabbitmq_url)

    stop_event = asyncio.Event()

    _install_signal_handlers(stop_event)

    await rabbitmq.connect()

    channel = await rabbitmq.open_channel(prefetch_count=PREFETCH_COUNT)

    try:
        await declare_topology(channel)

        queue = await channel.declare_queue(
            META_INBOUND_QUEUE,
            durable=True,
        )

        retry_exchange = await channel.declare_exchange(
            RETRY_EXCHANGE_NAME,
            ExchangeType.DIRECT,
            durable=True,
        )

        dead_letter_exchange = await channel.declare_exchange(
            DEAD_LETTER_EXCHANGE_NAME,
            ExchangeType.DIRECT,
            durable=True,
        )

        async def processor_bundle_factory(
            session: AsyncSession,
            tenant_id: UUID,
        ) -> tuple[
            IncomingMessageProcessor,
            MetaStatusProcessor,
        ]:
            return await build_meta_inbound_processors(
                session=session,
                tenant_id=tenant_id,
                presence_store=(presence_store),
            )

        handler = MetaInboundRabbitMQHandler(
            session_factory=session_factory,
            processor_bundle_factory=(processor_bundle_factory),
        )

        consumer = ReliableConsumer(
            queue_name=META_INBOUND_QUEUE,
            queue=queue,
            retry_exchange=retry_exchange,
            dead_letter_exchange=(dead_letter_exchange),
            handler=handler,
            max_attempts=5,
        )

        await consumer.start()

        print("Meta inbound worker started.")

        await stop_event.wait()

    finally:
        print("Meta inbound worker shutting down...")

        if not channel.is_closed:
            await channel.close()

        await rabbitmq.close()
        await redis.aclose()
        await database_engine.dispose()

        print("Meta inbound worker stopped.")


def _install_signal_handlers(
    stop_event: asyncio.Event,
) -> None:
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


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
