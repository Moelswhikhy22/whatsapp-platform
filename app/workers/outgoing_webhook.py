from __future__ import annotations

import asyncio
import signal
from uuid import UUID

import httpx
from aio_pika import ExchangeType
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from app.core.config import (
    get_settings,
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
    RETRY_EXCHANGE_NAME,
    WEBHOOK_DELIVERY_QUEUE,
    declare_topology,
)
from app.integrations.vault.client import (
    VaultClient,
    VaultClientConfig,
)
from app.integrations.webhooks.delivery import (
    WebhookHttpDeliveryClient,
)
from app.integrations.webhooks.signing_secret import (
    VaultWebhookSigningSecretProvider,
)
from app.integrations.webhooks.ssrf import (
    WebhookEndpointValidator,
)
from app.repositories.outgoing_webhook import (
    OutgoingWebhookDeliveryRepository,
)
from app.services.outgoing_webhook_delivery import (
    OutgoingWebhookDeliveryService,
)
from app.workers.outgoing_webhook_handler import (
    OutgoingWebhookRabbitMQHandler,
)


PREFETCH_COUNT = 10
WEBHOOK_MAX_ATTEMPTS = 5
WEBHOOK_HTTP_TIMEOUT_SECONDS = 10.0


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
            verify=(settings.vault_verify),
            timeout_seconds=(settings.vault_timeout_seconds),
            kv_mount_point=(settings.vault_kv_mount_point),
        )
    )

    signing_secret_provider = VaultWebhookSigningSecretProvider(vault_client)

    endpoint_validator = WebhookEndpointValidator()

    stop_event = asyncio.Event()

    _install_signal_handlers(stop_event)

    await rabbitmq.connect()

    channel = await rabbitmq.open_channel(prefetch_count=(PREFETCH_COUNT))

    try:
        await declare_topology(channel)

        queue = await channel.declare_queue(
            WEBHOOK_DELIVERY_QUEUE,
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

        timeout = httpx.Timeout(WEBHOOK_HTTP_TIMEOUT_SECONDS)

        async with httpx.AsyncClient(
            timeout=timeout,
        ) as http_client:
            delivery_client = WebhookHttpDeliveryClient(
                http_client=(http_client),
                endpoint_validator=(endpoint_validator),
            )

            def service_factory(
                session: AsyncSession,
                tenant_id: UUID,
            ) -> OutgoingWebhookDeliveryService:
                repository = OutgoingWebhookDeliveryRepository(
                    session=session,
                    tenant_id=(tenant_id),
                )

                return OutgoingWebhookDeliveryService(
                    repository=(repository),
                    signing_secret_provider=(signing_secret_provider),
                    delivery_client=(delivery_client),
                )

            handler = OutgoingWebhookRabbitMQHandler(
                session_factory=(session_factory),
                service_factory=(service_factory),
                max_attempts=(WEBHOOK_MAX_ATTEMPTS),
            )

            consumer = ReliableConsumer(
                queue_name=(WEBHOOK_DELIVERY_QUEUE),
                queue=queue,
                retry_exchange=(retry_exchange),
                dead_letter_exchange=(dead_letter_exchange),
                handler=handler,
                max_attempts=(WEBHOOK_MAX_ATTEMPTS),
            )

            await consumer.start()

            print(("Outgoing webhook worker started."))

            await stop_event.wait()

    finally:
        print(("Outgoing webhook worker shutting down..."))

        if not channel.is_closed:
            await channel.close()

        await rabbitmq.close()

        await vault_client.close()

        await database_engine.dispose()

        print(("Outgoing webhook worker stopped."))


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
