from __future__ import annotations

import json
from collections.abc import (
    Awaitable,
    Callable,
)
from dataclasses import dataclass
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
from app.services.meta_outbound import (
    MetaOutboundAmbiguousDeliveryError,
    MetaOutboundMessageNotFoundError,
    MetaOutboundOutcome,
    MetaOutboundResult,
    MetaOutboundSendService,
)
from app.workers.meta_outbound_dependencies import (
    MetaOutboundTenantNotFoundError,
)


ServiceFactory = Callable[
    [AsyncSession, UUID],
    Awaitable[MetaOutboundSendService],
]


@dataclass(frozen=True, slots=True)
class MetaOutboundJob:
    tenant_id: UUID
    message_id: UUID


class InvalidMetaOutboundJobError(PermanentMessageError):
    pass


class MetaOutboundRabbitMQHandler:
    def __init__(
        self,
        *,
        session_factory: (async_sessionmaker[AsyncSession]),
        service_factory: ServiceFactory,
    ) -> None:
        self._session_factory = session_factory
        self._service_factory = service_factory

    async def __call__(
        self,
        message: AbstractIncomingMessage,
    ) -> None:
        job = self._parse_job(message.body)

        try:
            result = await self._dispatch(job)

        except (
            MetaOutboundMessageNotFoundError,
            MetaOutboundTenantNotFoundError,
        ) as exc:
            raise PermanentMessageError(("Meta outbound resource was not found.")) from exc

        except MetaOutboundAmbiguousDeliveryError as exc:
            raise PermanentMessageError(
                ("Meta outbound delivery is ambiguous and requires manual review.")
            ) from exc

        if result.outcome is MetaOutboundOutcome.PERMANENT_FAILURE:
            raise PermanentMessageError(result.failure_code or ("Permanent Meta outbound failure."))

    async def _dispatch(
        self,
        job: MetaOutboundJob,
    ) -> MetaOutboundResult:
        async with self._session_factory() as session:
            async with session.begin():
                service = await self._service_factory(
                    session,
                    job.tenant_id,
                )

                return await service.send(message_id=job.message_id)

    @staticmethod
    def _parse_job(
        body: bytes,
    ) -> MetaOutboundJob:
        try:
            decoded = json.loads(body)
        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
        ) as exc:
            raise InvalidMetaOutboundJobError(("Meta outbound job is not valid JSON.")) from exc

        if not isinstance(decoded, dict):
            raise InvalidMetaOutboundJobError(("Meta outbound job must be an object."))

        envelope = cast(
            dict[str, object],
            decoded,
        )

        if envelope.get("event_type") != "meta.outbound.send":
            raise InvalidMetaOutboundJobError(("Unexpected Meta outbound event type."))

        raw_tenant_id = envelope.get("tenant_id")

        if not isinstance(
            raw_tenant_id,
            str,
        ):
            raise InvalidMetaOutboundJobError("tenant_id is missing.")

        raw_payload = envelope.get("payload")

        if not isinstance(
            raw_payload,
            dict,
        ):
            raise InvalidMetaOutboundJobError(("Meta outbound payload is missing."))

        payload = cast(
            dict[str, object],
            raw_payload,
        )

        raw_message_id = payload.get("message_id")

        if not isinstance(
            raw_message_id,
            str,
        ):
            raise InvalidMetaOutboundJobError("message_id is missing.")

        if envelope.get("aggregate_type") != "message":
            raise InvalidMetaOutboundJobError(("Meta outbound aggregate type is invalid."))

        raw_aggregate_id = envelope.get("aggregate_id")

        if (
            not isinstance(
                raw_aggregate_id,
                str,
            )
            or raw_aggregate_id != raw_message_id
        ):
            raise InvalidMetaOutboundJobError(
                ("Meta outbound aggregate ID does not match message_id.")
            )

        try:
            tenant_id = UUID(raw_tenant_id)
            message_id = UUID(raw_message_id)
        except ValueError as exc:
            raise InvalidMetaOutboundJobError(
                ("Meta outbound job contains an invalid UUID.")
            ) from exc

        return MetaOutboundJob(
            tenant_id=tenant_id,
            message_id=message_id,
        )
