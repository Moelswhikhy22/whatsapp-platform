import httpx
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.http import create_http_client
from app.core.redis import create_redis_client
from app.db.session import create_database_engine
from app.integrations.rabbitmq.client import RabbitMQClient
from app.integrations.s3.client import (
    ManagedS3Client,
    S3ClientConfig,
)
from app.integrations.vault.client import (
    VaultClient,
    VaultClientConfig,
)


async def test_async_database_engine_can_be_created() -> None:
    engine = create_database_engine("postgresql+psycopg://user:password@localhost/test")

    assert isinstance(engine, AsyncEngine)

    await engine.dispose()


async def test_redis_client_can_be_created_and_closed() -> None:
    client = create_redis_client("redis://localhost:6379/0")

    assert isinstance(client, Redis)

    await client.aclose()


def test_rabbitmq_client_starts_disconnected() -> None:
    client = RabbitMQClient("amqp://guest:guest@localhost/")

    assert client.is_connected is False


def test_s3_client_can_be_created() -> None:
    config = S3ClientConfig(
        region_name="us-east-1",
        endpoint_url="http://localhost:9000",
        addressing_style="path",
    )

    client = ManagedS3Client(config)

    assert isinstance(client, ManagedS3Client)


async def test_vault_client_can_be_created_and_closed() -> None:
    client = VaultClient(
        VaultClientConfig(
            url="http://127.0.0.1:8200",
        )
    )

    assert isinstance(client, VaultClient)

    await client.close()


async def test_http_client_can_be_created_and_closed() -> None:
    client = create_http_client()

    assert isinstance(client, httpx.AsyncClient)

    await client.aclose()
