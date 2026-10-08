from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from app.db.models.raw_webhook_event import (
    RawWebhookEvent,
    RawWebhookProcessingStatus,
)
from app.integrations.meta.payload_classifier import (
    classify_meta_payload,
)
from app.repositories.raw_webhook_processing import (
    RawWebhookProcessingRepository,
)
from app.services.incoming_message import (
    IncomingMessageProcessor,
    IncomingMessageUnresolvedError,
)


class MetaInboundPipelineIncompleteError(RuntimeError):
    pass


class MetaInboundRawEventNotFoundError(RuntimeError):
    pass


class MetaInboundDispatchOutcome(StrEnum):
    PROCESSED = "processed"
    ALREADY_PROCESSED = "already_processed"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True, slots=True)
class MetaInboundDispatchResult:
    outcome: MetaInboundDispatchOutcome
    raw_event_id: UUID
    error_code: str | None = None


class MetaStatusProcessor(Protocol):
    async def process_raw_event(
        self,
        raw_event: RawWebhookEvent,
    ) -> object: ...


class MetaInboundDispatchService:
    def __init__(
        self,
        *,
        repository: RawWebhookProcessingRepository,
        message_processor: IncomingMessageProcessor,
        status_processor: MetaStatusProcessor | None = None,
    ) -> None:
        self._repository = repository
        self._message_processor = message_processor
        self._status_processor = status_processor

    async def dispatch(
        self,
        *,
        raw_event_id: UUID,
    ) -> MetaInboundDispatchResult:
        raw_event = await self._repository.lock_meta_event(raw_event_id)

        if raw_event is None:
            raise MetaInboundRawEventNotFoundError

        if raw_event.processing_status is RawWebhookProcessingStatus.PROCESSED:
            return MetaInboundDispatchResult(
                outcome=(MetaInboundDispatchOutcome.ALREADY_PROCESSED),
                raw_event_id=raw_event.id,
            )

        if raw_event.tenant_id is None:
            code = "RAW_EVENT_TENANT_UNRESOLVED"

            self._repository.mark_unresolved(
                raw_event,
                error=code,
            )

            return MetaInboundDispatchResult(
                outcome=(MetaInboundDispatchOutcome.UNRESOLVED),
                raw_event_id=raw_event.id,
                error_code=code,
            )

        self._repository.mark_processing(raw_event)

        parts = classify_meta_payload(raw_event.payload_json)

        if not parts.has_messages and not parts.has_statuses and not parts.has_message_echoes:
            code = "META_EVENT_KIND_UNSUPPORTED"

            self._repository.mark_unresolved(
                raw_event,
                error=code,
            )

            return MetaInboundDispatchResult(
                outcome=(MetaInboundDispatchOutcome.UNRESOLVED),
                raw_event_id=raw_event.id,
                error_code=code,
            )

        if parts.has_messages or parts.has_message_echoes:
            try:
                await self._message_processor.process_raw_event(raw_event)
            except IncomingMessageUnresolvedError as exc:
                self._repository.mark_unresolved(
                    raw_event,
                    error=exc.code,
                )

                return MetaInboundDispatchResult(
                    outcome=(MetaInboundDispatchOutcome.UNRESOLVED),
                    raw_event_id=raw_event.id,
                    error_code=exc.code,
                )

        if parts.has_statuses:
            if self._status_processor is None:
                raise MetaInboundPipelineIncompleteError(
                    "Meta status payload requires the status processor."
                )

            await self._status_processor.process_raw_event(raw_event)

        self._repository.mark_processed(raw_event)

        return MetaInboundDispatchResult(
            outcome=(MetaInboundDispatchOutcome.PROCESSED),
            raw_event_id=raw_event.id,
        )
