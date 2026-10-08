from __future__ import annotations

import asyncio
import signal
from uuid import UUID

import httpx
from aio_pika import ExchangeType
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from app.core.config import get_settings
from app.db.session import (
    create_database_engine,
    create_session_factory,
)
from app.integrations.meta.client import (
    MetaCloudAPIClient,
)
from app.integrations.meta.vault_outbound_credentials import (
    VaultMetaOutboundCredentialProvider,
)
from app.integrations.rabbitmq.client import (
    RabbitMQClient,
)
from app.integrations.rabbitmq.consumer import (
    ReliableConsumer,
)
from app.integrations.rabbitmq.topology import (
    DEAD_LETTER_EXCHANGE_NAME,
    META_OUTBOUND_QUEUE,
    RETRY_EXCHANGE_NAME,
    declare_topology,
)
from app.integrations.vault.client import (
    VaultClient,
    VaultClientConfig,
)
from app.services.meta_outbound import (
    MetaOutboundSendService,
)
from app.workers.meta_outbound_dependencies import (
    build_meta_outbound_service,
)
from app.workers.meta_outbound_handler import (
    MetaOutboundRabbitMQHandler,
)


PREFETCH_COUNT = 10


async def run_worker() -> None:
    settings = get_settings()

    database_engine = create_database_engine(settings.database_url)

    session_factory = create_session_factory(database_engine)

    rabbitmq = RabbitMQClient(settings.rabbitmq_url)

    vault_client = VaultClient(
        VaultClientConfig(
            url=settings.vault_addr,
            token=(settings.vault_token or None),
            namespace=(settings.vault_namespace or None),
            verify=settings.vault_verify,
            timeout_seconds=(settings.vault_timeout_seconds),
            kv_mount_point=(settings.vault_kv_mount_point),
        )
    )

    credential_provider = VaultMetaOutboundCredentialProvider(vault_client)

    stop_event = asyncio.Event()

    _install_signal_handlers(stop_event)

    await rabbitmq.connect()

    channel = await rabbitmq.open_channel(prefetch_count=PREFETCH_COUNT)

    try:
        await declare_topology(channel)

        queue = await channel.declare_queue(
            META_OUTBOUND_QUEUE,
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

        timeout = httpx.Timeout(settings.meta_http_timeout_seconds)

        async with httpx.AsyncClient(timeout=timeout) as http_client:
            meta_client = MetaCloudAPIClient(http_client)

            async def service_factory(
                session: AsyncSession,
                tenant_id: UUID,
            ) -> MetaOutboundSendService:
                return await build_meta_outbound_service(
                    session=session,
                    tenant_id=tenant_id,
                    credential_provider=(credential_provider),
                    meta_client=(meta_client),
                )

            handler = MetaOutboundRabbitMQHandler(
                session_factory=(session_factory),
                service_factory=(service_factory),
            )

            consumer = ReliableConsumer(
                queue_name=(META_OUTBOUND_QUEUE),
                queue=queue,
                retry_exchange=(retry_exchange),
                dead_letter_exchange=(dead_letter_exchange),
                handler=handler,
                max_attempts=5,
            )

            await consumer.start()

            print(("Meta outbound worker started."))

            await stop_event.wait()

    finally:
        print(("Meta outbound worker shutting down..."))

        if not channel.is_closed:
            await channel.close()

        await rabbitmq.close()

        await vault_client.close()

        await database_engine.dispose()

        print(("Meta outbound worker stopped."))


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
