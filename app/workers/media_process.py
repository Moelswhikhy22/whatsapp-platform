from __future__ import annotations

import asyncio
import signal
from uuid import UUID

import httpx
from aio_pika import ExchangeType
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import (
    create_database_engine,
    create_session_factory,
)
from app.integrations.meta.media_client import (
    MetaMediaAPIClient,
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
    MEDIA_PROCESS_QUEUE,
    RETRY_EXCHANGE_NAME,
    declare_topology,
)
from app.integrations.s3.client import (
    ManagedS3Client,
    S3ClientConfig,
)
from app.integrations.vault.client import (
    VaultClient,
    VaultClientConfig,
)
from app.repositories.media import (
    MediaRepository,
)
from app.repositories.meta_media import (
    MetaMediaRepository,
)
from app.services.media_object_key import (
    MediaObjectKeyBuilder,
)
from app.services.media_upload import (
    MediaUploadService,
)
from app.services.meta_media import (
    MetaMediaProcessingService,
)
from app.workers.media_process_handler import (
    MediaProcessRabbitMQHandler,
)


PREFETCH_COUNT = 4


async def run_worker() -> None:
    settings = get_settings()

    database_engine = create_database_engine(settings.database_url)

    session_factory = create_session_factory(database_engine)

    rabbitmq = RabbitMQClient(settings.rabbitmq_url)

    vault_client = VaultClient(
        VaultClientConfig(
            url=settings.vault_addr,
            token=settings.vault_token or None,
            namespace=(settings.vault_namespace or None),
            verify=settings.vault_verify,
            timeout_seconds=(settings.vault_timeout_seconds),
            kv_mount_point=(settings.vault_kv_mount_point),
        )
    )

    credential_provider = VaultMetaOutboundCredentialProvider(vault_client)

    s3_client = ManagedS3Client(
        S3ClientConfig(
            region_name=settings.s3_region,
            endpoint_url=(settings.s3_endpoint_url),
            access_key_id=(settings.s3_access_key_id),
            secret_access_key=(settings.s3_secret_access_key),
            session_token=(settings.s3_session_token),
            addressing_style=(settings.s3_addressing_style),
        )
    )

    key_builder = MediaObjectKeyBuilder(environment=settings.app_env)

    stop_event = asyncio.Event()

    _install_signal_handlers(stop_event)

    await rabbitmq.connect()

    channel = await rabbitmq.open_channel(prefetch_count=PREFETCH_COUNT)

    try:
        await declare_topology(channel)

        queue = await channel.declare_queue(
            MEDIA_PROCESS_QUEUE,
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

        timeout = httpx.Timeout(
            timeout=60.0,
            connect=(settings.meta_http_timeout_seconds),
        )

        async with httpx.AsyncClient(timeout=timeout) as http_client:
            meta_client = MetaMediaAPIClient(http_client)

            def service_factory(
                session: AsyncSession,
                tenant_id: UUID,
            ) -> MetaMediaProcessingService:
                media_repository = MediaRepository(
                    session=session,
                    tenant_id=tenant_id,
                )

                meta_repository = MetaMediaRepository(
                    session=session,
                    tenant_id=tenant_id,
                )

                upload_service = MediaUploadService(
                    repository=(media_repository),
                    storage=s3_client,
                    bucket=(settings.s3_bucket),
                    key_builder=(key_builder),
                    retention_days=(settings.media_retention_days),
                )

                return MetaMediaProcessingService(
                    repository=(meta_repository),
                    media_repository=(media_repository),
                    credential_provider=(credential_provider),
                    meta_client=(meta_client),
                    upload_service=(upload_service),
                )

            handler = MediaProcessRabbitMQHandler(
                session_factory=(session_factory),
                service_factory=(service_factory),
            )

            consumer = ReliableConsumer(
                queue_name=(MEDIA_PROCESS_QUEUE),
                queue=queue,
                retry_exchange=(retry_exchange),
                dead_letter_exchange=(dead_letter_exchange),
                handler=handler,
                max_attempts=5,
            )

            await consumer.start()

            print("Media process worker started.")

            await stop_event.wait()

    finally:
        print("Media process worker shutting down...")

        if not channel.is_closed:
            await channel.close()

        await rabbitmq.close()

        await vault_client.close()

        await database_engine.dispose()

        print("Media process worker stopped.")


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
