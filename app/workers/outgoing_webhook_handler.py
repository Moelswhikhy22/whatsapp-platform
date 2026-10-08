from __future__ import annotations

import json
from collections.abc import Callable
from typing import cast
from uuid import UUID

from aio_pika.abc import (
    AbstractIncomingMessage,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
)

from app.integrations.rabbitmq.consumer import (
    PermanentMessageError,
)
from app.services.outgoing_webhook_delivery import (
    OutgoingWebhookDeliveryService,
    OutgoingWebhookEvent,
    OutgoingWebhookProcessResult,
    OutgoingWebhookRetryDeliveryNotFoundError,
    OutgoingWebhookRetryRequest,
)
from app.services.outgoing_webhook_management import (
    OUTGOING_WEBHOOK_RETRY_REQUESTED_EVENT,
)


ServiceFactory = Callable[
    [AsyncSession, UUID],
    OutgoingWebhookDeliveryService,
]


OutgoingWebhookJob = OutgoingWebhookEvent | OutgoingWebhookRetryRequest


class InvalidOutgoingWebhookJobError(PermanentMessageError):
    """Broker envelope is permanently invalid."""


class OutgoingWebhookRetryRequiredError(RuntimeError):
    """
    Raised only after the current attempt
    has been persisted successfully.

    ReliableConsumer then moves the broker
    message through retry/DLQ handling.
    """


class OutgoingWebhookRabbitMQHandler:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        service_factory: ServiceFactory,
        max_attempts: int = 5,
    ) -> None:
        if max_attempts <= 0:
            raise ValueError(("max_attempts must be greater than zero"))

        self._session_factory = session_factory
        self._service_factory = service_factory
        self._max_attempts = max_attempts

    async def __call__(
        self,
        message: AbstractIncomingMessage,
    ) -> None:
        job = self._parse_job(message.body)

        final_attempt = self._is_final_attempt(message)

        try:
            result = await self._dispatch(
                job=job,
                final_attempt=(final_attempt),
            )

        except OutgoingWebhookRetryDeliveryNotFoundError as exc:
            raise PermanentMessageError(("Outgoing webhook retry target was not found.")) from exc

        if result.retry_required:
            raise (OutgoingWebhookRetryRequiredError(("Outgoing webhook delivery requires retry.")))

    async def _dispatch(
        self,
        *,
        job: OutgoingWebhookJob,
        final_attempt: bool,
    ) -> OutgoingWebhookProcessResult:
        async with self._session_factory() as session:
            async with session.begin():
                service = self._service_factory(
                    session,
                    job.tenant_id,
                )

                if isinstance(
                    job,
                    OutgoingWebhookRetryRequest,
                ):
                    return await service.process_retry_request(
                        request=job,
                        final_attempt=(final_attempt),
                    )

                return await service.process_event(
                    event=job,
                    final_attempt=(final_attempt),
                )

    def _is_final_attempt(
        self,
        message: AbstractIncomingMessage,
    ) -> bool:
        retry_count = self._retry_count(message)

        current_attempt = retry_count + 1

        return current_attempt >= self._max_attempts

    @staticmethod
    def _retry_count(
        message: AbstractIncomingMessage,
    ) -> int:
        value = (message.headers or {}).get(
            "x-retry-count",
            0,
        )

        if (
            isinstance(
                value,
                int,
            )
            and not isinstance(
                value,
                bool,
            )
            and value >= 0
        ):
            return value

        return 0

    @classmethod
    def _parse_job(
        cls,
        body: bytes,
    ) -> OutgoingWebhookJob:
        envelope = cls._decode_envelope(body)

        raw_event_type = envelope.get("event_type")

        if (
            not isinstance(
                raw_event_type,
                str,
            )
            or not raw_event_type.strip()
        ):
            raise (InvalidOutgoingWebhookJobError(("event_type is missing.")))

        event_type = raw_event_type.strip().lower()

        if event_type == (OUTGOING_WEBHOOK_RETRY_REQUESTED_EVENT):
            return cls._parse_retry_request(envelope)

        return cls._parse_event_envelope(envelope)

    @staticmethod
    def _decode_envelope(
        body: bytes,
    ) -> dict[str, object]:
        try:
            decoded = json.loads(body)

        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
        ) as exc:
            raise (
                InvalidOutgoingWebhookJobError(("Outgoing webhook job is not valid JSON."))
            ) from exc

        if not isinstance(
            decoded,
            dict,
        ):
            raise (InvalidOutgoingWebhookJobError(("Outgoing webhook job must be an object.")))

        return cast(
            dict[str, object],
            decoded,
        )

    @classmethod
    def _parse_retry_request(
        cls,
        envelope: dict[str, object],
    ) -> OutgoingWebhookRetryRequest:
        tenant_id = cls._required_uuid(
            envelope,
            "tenant_id",
        )

        raw_payload = envelope.get("payload")

        if not isinstance(
            raw_payload,
            dict,
        ):
            raise (InvalidOutgoingWebhookJobError(("Outgoing webhook retry payload is missing.")))

        payload = cast(
            dict[str, object],
            raw_payload,
        )

        delivery_id = cls._required_uuid(
            payload,
            "delivery_id",
        )

        return OutgoingWebhookRetryRequest(
            tenant_id=tenant_id,
            delivery_id=(delivery_id),
        )

    @classmethod
    def _parse_event_envelope(
        cls,
        envelope: dict[str, object],
    ) -> OutgoingWebhookEvent:
        event_id = cls._required_uuid(
            envelope,
            "event_id",
        )

        tenant_id = cls._required_uuid(
            envelope,
            "tenant_id",
        )

        raw_event_type = envelope.get("event_type")

        raw_aggregate_type = envelope.get("aggregate_type")

        raw_aggregate_id = envelope.get("aggregate_id")

        raw_occurred_at = envelope.get("occurred_at")

        raw_payload = envelope.get("payload")

        if (
            not isinstance(
                raw_event_type,
                str,
            )
            or not raw_event_type.strip()
        ):
            raise (InvalidOutgoingWebhookJobError(("event_type is missing.")))

        if (
            not isinstance(
                raw_aggregate_type,
                str,
            )
            or not raw_aggregate_type.strip()
        ):
            raise (InvalidOutgoingWebhookJobError(("aggregate_type is missing.")))

        if (
            not isinstance(
                raw_aggregate_id,
                str,
            )
            or not raw_aggregate_id.strip()
        ):
            raise (InvalidOutgoingWebhookJobError(("aggregate_id is missing.")))

        if (
            not isinstance(
                raw_occurred_at,
                str,
            )
            or not raw_occurred_at.strip()
        ):
            raise (InvalidOutgoingWebhookJobError(("occurred_at is missing.")))

        if not isinstance(
            raw_payload,
            dict,
        ):
            raise (InvalidOutgoingWebhookJobError(("Outgoing webhook payload is missing.")))

        payload = cast(
            dict[str, object],
            raw_payload,
        )

        return OutgoingWebhookEvent(
            event_id=event_id,
            tenant_id=tenant_id,
            event_type=(raw_event_type.strip()),
            aggregate_type=(raw_aggregate_type.strip()),
            aggregate_id=(raw_aggregate_id.strip()),
            occurred_at=(raw_occurred_at.strip()),
            payload=payload,
        )

    @staticmethod
    def _required_uuid(
        payload: dict[str, object],
        field: str,
    ) -> UUID:
        raw_value = payload.get(field)

        if not isinstance(
            raw_value,
            str,
        ):
            raise (InvalidOutgoingWebhookJobError(f"{field} is missing."))

        try:
            return UUID(raw_value)

        except ValueError as exc:
            raise (InvalidOutgoingWebhookJobError((f"{field} must be a valid UUID."))) from exc

    @classmethod
    def _parse_event(
        cls,
        body: bytes,
    ) -> OutgoingWebhookEvent:
        """
        Backward-compatible helper retained for
        the existing unit tests.
        """

        job = cls._parse_job(body)

        if isinstance(
            job,
            OutgoingWebhookRetryRequest,
        ):
            raise (
                InvalidOutgoingWebhookJobError(("Expected domain event, received retry request."))
            )

        return job
