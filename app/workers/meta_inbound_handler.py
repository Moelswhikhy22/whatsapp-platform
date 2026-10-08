from __future__ import annotations

import json
from collections.abc import (
    Awaitable,
    Callable,
)
from typing import cast
from uuid import UUID

from aio_pika.abc import (
    AbstractIncomingMessage,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
)

from app.db.models.raw_webhook_event import (
    RawWebhookProcessingStatus,
)
from app.integrations.rabbitmq.consumer import (
    PermanentMessageError,
)
from app.repositories.raw_webhook_processing import (
    RawWebhookProcessingRepository,
)
from app.services.incoming_message import (
    IncomingMessageProcessor,
)
from app.services.meta_inbound_dispatcher import (
    MetaInboundDispatchOutcome,
    MetaInboundDispatchResult,
    MetaInboundDispatchService,
    MetaInboundRawEventNotFoundError,
    MetaStatusProcessor,
)


ProcessorBundleFactory = Callable[
    [AsyncSession, UUID],
    Awaitable[
        tuple[
            IncomingMessageProcessor,
            MetaStatusProcessor,
        ]
    ],
]


class InvalidMetaInboundJobError(PermanentMessageError):
    pass


class MetaInboundRabbitMQHandler:
    def __init__(
        self,
        *,
        session_factory: (async_sessionmaker[AsyncSession]),
        processor_bundle_factory: (ProcessorBundleFactory),
    ) -> None:
        self._session_factory = session_factory

        self._processor_bundle_factory = processor_bundle_factory

    async def __call__(
        self,
        message: AbstractIncomingMessage,
    ) -> None:
        raw_event_id = self._parse_job(message.body)

        try:
            result = await self._dispatch(raw_event_id)

        except MetaInboundRawEventNotFoundError as exc:
            raise PermanentMessageError("Meta raw event was not found.") from exc

        except Exception as exc:
            await self._record_failure(
                raw_event_id=raw_event_id,
                exc=exc,
            )

            raise

        if result.outcome is MetaInboundDispatchOutcome.UNRESOLVED:
            raise PermanentMessageError(result.error_code or ("Meta inbound event is unresolved."))

    async def _dispatch(
        self,
        raw_event_id: UUID,
    ) -> MetaInboundDispatchResult:
        async with self._session_factory() as session:
            async with session.begin():
                repository = RawWebhookProcessingRepository(session)

                raw_event = await repository.lock_meta_event(raw_event_id)

                if raw_event is None:
                    raise (MetaInboundRawEventNotFoundError)

                if raw_event.processing_status is RawWebhookProcessingStatus.PROCESSED:
                    return MetaInboundDispatchResult(
                        outcome=(MetaInboundDispatchOutcome.ALREADY_PROCESSED),
                        raw_event_id=(raw_event.id),
                    )

                if raw_event.tenant_id is None:
                    repository.mark_unresolved(
                        raw_event,
                        error=("RAW_EVENT_TENANT_UNRESOLVED"),
                    )

                    return MetaInboundDispatchResult(
                        outcome=(MetaInboundDispatchOutcome.UNRESOLVED),
                        raw_event_id=(raw_event.id),
                        error_code=("RAW_EVENT_TENANT_UNRESOLVED"),
                    )

                (
                    message_processor,
                    status_processor,
                ) = await self._processor_bundle_factory(
                    session,
                    raw_event.tenant_id,
                )

                service = MetaInboundDispatchService(
                    repository=repository,
                    message_processor=(message_processor),
                    status_processor=(status_processor),
                )

                return await service.dispatch(raw_event_id=raw_event_id)

    async def _record_failure(
        self,
        *,
        raw_event_id: UUID,
        exc: Exception,
    ) -> None:
        safe_error = f"{type(exc).__name__}: Meta inbound processing failed"

        async with self._session_factory() as session:
            async with session.begin():
                repository = RawWebhookProcessingRepository(session)

                await repository.record_failed_attempt(
                    raw_event_id=(raw_event_id),
                    error=safe_error,
                )

    @staticmethod
    def _parse_job(
        body: bytes,
    ) -> UUID:
        try:
            decoded = json.loads(body)
        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
        ) as exc:
            raise InvalidMetaInboundJobError(("Meta inbound job is not valid JSON.")) from exc

        if not isinstance(decoded, dict):
            raise InvalidMetaInboundJobError(("Meta inbound job must be an object."))

        envelope = cast(
            dict[str, object],
            decoded,
        )

        event_type = envelope.get("event_type")

        if event_type != "meta.inbound.raw_event":
            raise InvalidMetaInboundJobError(("Unexpected Meta inbound event type."))

        raw_payload = envelope.get("payload")

        if not isinstance(
            raw_payload,
            dict,
        ):
            raise InvalidMetaInboundJobError(("Meta inbound payload is missing."))

        payload = cast(
            dict[str, object],
            raw_payload,
        )

        raw_id = payload.get("raw_event_id")

        if not isinstance(raw_id, str):
            raise InvalidMetaInboundJobError("raw_event_id is missing.")

        try:
            return UUID(raw_id)
        except ValueError as exc:
            raise InvalidMetaInboundJobError("raw_event_id is invalid.") from exc
