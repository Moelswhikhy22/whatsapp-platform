from unittest.mock import (
    AsyncMock,
    MagicMock,
)

import pytest

import app.integrations.rabbitmq.client as client_module
from app.integrations.rabbitmq.client import (
    RabbitMQClient,
)


@pytest.mark.asyncio
async def test_client_uses_robust_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = MagicMock()
    connection.is_closed = False
    connection.close = AsyncMock()

    connect_robust = AsyncMock(
        return_value=connection,
    )

    monkeypatch.setattr(
        client_module,
        "connect_robust",
        connect_robust,
    )

    client = RabbitMQClient(
        "amqp://example/",
    )

    await client.connect()

    connect_robust.assert_awaited_once_with(
        "amqp://example/",
        client_properties={
            "connection_name": ("whatsapp-platform"),
        },
    )

    assert client.is_connected


@pytest.mark.asyncio
async def test_channel_enables_confirms_and_qos(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    channel = MagicMock()
    channel.set_qos = AsyncMock()

    connection = MagicMock()
    connection.is_closed = False

    connection.channel = AsyncMock(
        return_value=channel,
    )

    connect_robust = AsyncMock(
        return_value=connection,
    )

    monkeypatch.setattr(
        client_module,
        "connect_robust",
        connect_robust,
    )

    client = RabbitMQClient(
        "amqp://example/",
    )

    await client.connect()

    result = await client.open_channel(
        prefetch_count=20,
    )

    assert result is channel

    connection.channel.assert_awaited_once_with(
        publisher_confirms=True,
        on_return_raises=True,
    )

    channel.set_qos.assert_awaited_once_with(
        prefetch_count=20,
    )
