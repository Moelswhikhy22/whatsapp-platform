from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from app.db.models.raw_webhook_event import (
    RawWebhookEvent,
)
from app.integrations.meta.status_parser import (
    parse_meta_message_statuses,
)
from app.repositories.message_status import (
    MessageStatusRepository,
)
from app.services.message_status_semantics import (
    should_advance_message_status,
)


class MessageStatusProcessingError(RuntimeError):
    pass


class MessageStatusMessageNotFoundError(MessageStatusProcessingError):
    pass


class MessageStatusOutcome(StrEnum):
    PROCESSED = "processed"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True, slots=True)
class MessageStatusProcessResult:
    outcome: MessageStatusOutcome
    history_event_count: int = 0
    effective_status_change_count: int = 0


class MessageStatusProcessor:
    def __init__(
        self,
        *,
        repository: MessageStatusRepository,
    ) -> None:
        self._repository = repository

    async def process_raw_event(
        self,
        raw_event: RawWebhookEvent,
    ) -> MessageStatusProcessResult:
        if raw_event.tenant_id is None:
            raise MessageStatusProcessingError("Raw event tenant is unresolved.")

        if raw_event.tenant_id != self._repository.tenant_id:
            raise MessageStatusProcessingError("Raw event tenant mismatch.")

        statuses = parse_meta_message_statuses(raw_event.payload_json)

        if not statuses:
            return MessageStatusProcessResult(outcome=(MessageStatusOutcome.NOT_APPLICABLE))

        history_count = 0
        effective_change_count = 0

        for parsed in statuses:
            message = await self._repository.get_outbound_message_for_update(parsed.meta_message_id)

            if message is None:
                raise (
                    MessageStatusMessageNotFoundError(
                        (f"Outbound message not found for Meta ID {parsed.meta_message_id!r}.")
                    )
                )

            self._repository.add_status_history(
                message_id=message.id,
                status=parsed.status,
                meta_timestamp=(parsed.meta_timestamp),
            )

            history_count += 1

            if not should_advance_message_status(
                current=message.status,
                incoming=parsed.status,
            ):
                continue

            self._repository.set_effective_status(
                message=message,
                status=parsed.status,
            )

            self._repository.add_status_outbox_event(
                message=message,
                status=parsed.status,
            )

            effective_change_count += 1

        return MessageStatusProcessResult(
            outcome=(MessageStatusOutcome.PROCESSED),
            history_event_count=history_count,
            effective_status_change_count=(effective_change_count),
        )
