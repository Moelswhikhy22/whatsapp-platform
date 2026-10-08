from __future__ import annotations

from collections.abc import Awaitable, Callable

from aio_pika import DeliveryMode, Message
from aio_pika.abc import (
    AbstractExchange,
    AbstractIncomingMessage,
    AbstractQueue,
)
from pamqp.common import FieldTable

from app.integrations.rabbitmq.topology import (
    dead_letter_queue_name,
    retry_queue_name,
)

MessageHandler = Callable[
    [AbstractIncomingMessage],
    Awaitable[None],
]


class PermanentMessageError(Exception):
    """Raised when retrying a message cannot succeed."""


class ReliableConsumer:
    def __init__(
        self,
        *,
        queue_name: str,
        queue: AbstractQueue,
        retry_exchange: AbstractExchange,
        dead_letter_exchange: AbstractExchange,
        handler: MessageHandler,
        max_attempts: int = 5,
    ) -> None:
        if max_attempts <= 0:
            raise ValueError("max_attempts must be greater than zero")

        self._queue_name = queue_name
        self._queue = queue
        self._retry_exchange = retry_exchange
        self._dead_letter_exchange = dead_letter_exchange
        self._handler = handler
        self._max_attempts = max_attempts

    async def start(self) -> None:
        await self._queue.consume(
            self.handle_message,
            no_ack=False,
        )

    async def handle_message(
        self,
        message: AbstractIncomingMessage,
    ) -> None:
        try:
            await self._handler(message)
        except PermanentMessageError:
            await self._dead_letter_or_requeue(
                message,
                reason="permanent_failure",
            )
            return
        except Exception:
            await self._retry_or_dead_letter(
                message,
            )
            return

        await message.ack()

    async def _retry_or_dead_letter(
        self,
        message: AbstractIncomingMessage,
    ) -> None:
        retry_count = self._retry_count(
            message,
        )

        current_attempt = retry_count + 1

        if current_attempt >= self._max_attempts:
            await self._dead_letter_or_requeue(
                message,
                reason="max_attempts_exhausted",
            )
            return

        headers: FieldTable = dict(message.headers or {})

        headers["x-retry-count"] = retry_count + 1

        retry_message = self._copy_message(
            message,
            headers=headers,
        )

        try:
            await self._retry_exchange.publish(
                retry_message,
                routing_key=retry_queue_name(
                    self._queue_name,
                ),
                mandatory=True,
            )
        except Exception:
            await message.nack(
                requeue=True,
            )
            return

        await message.ack()

    async def _dead_letter_or_requeue(
        self,
        message: AbstractIncomingMessage,
        *,
        reason: str,
    ) -> None:
        headers: FieldTable = dict(message.headers or {})

        headers["x-dead-letter-reason"] = reason

        dead_message = self._copy_message(
            message,
            headers=headers,
        )

        try:
            await self._dead_letter_exchange.publish(
                dead_message,
                routing_key=dead_letter_queue_name(
                    self._queue_name,
                ),
                mandatory=True,
            )
        except Exception:
            await message.nack(
                requeue=True,
            )
            return

        await message.ack()

    @staticmethod
    def _retry_count(
        message: AbstractIncomingMessage,
    ) -> int:
        value = (message.headers or {}).get(
            "x-retry-count",
            0,
        )

        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            return value

        return 0

    @staticmethod
    def _copy_message(
        message: AbstractIncomingMessage,
        *,
        headers: FieldTable,
    ) -> Message:
        return Message(
            body=message.body,
            content_type=message.content_type,
            content_encoding=(message.content_encoding),
            delivery_mode=DeliveryMode.PERSISTENT,
            message_id=message.message_id,
            correlation_id=(message.correlation_id),
            type=message.type,
            headers=headers,
        )
