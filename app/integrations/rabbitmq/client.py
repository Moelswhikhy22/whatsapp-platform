from __future__ import annotations

from aio_pika import connect_robust
from aio_pika.abc import (
    AbstractRobustChannel,
    AbstractRobustConnection,
)


class RabbitMQClient:
    def __init__(self, url: str) -> None:
        self._url = url
        self._connection: AbstractRobustConnection | None = None

    @property
    def is_connected(self) -> bool:
        return self._connection is not None and not self._connection.is_closed

    async def connect(self) -> None:
        if self.is_connected:
            return

        self._connection = await connect_robust(
            self._url,
            client_properties={
                "connection_name": "whatsapp-platform",
            },
        )

    async def open_channel(
        self,
        *,
        prefetch_count: int | None = None,
    ) -> AbstractRobustChannel:
        if not self.is_connected or self._connection is None:
            raise RuntimeError("RabbitMQ client is not connected.")

        channel = await self._connection.channel(
            publisher_confirms=True,
            on_return_raises=True,
        )

        if prefetch_count is not None:
            await channel.set_qos(
                prefetch_count=prefetch_count,
            )

        return channel

    async def close(self) -> None:
        if self._connection is None:
            return

        if not self._connection.is_closed:
            await self._connection.close()

        self._connection = None
