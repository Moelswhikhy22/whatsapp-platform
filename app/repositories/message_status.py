from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.message import (
    Message,
    MessageDirection,
    MessageStatus,
)
from app.db.models.message_status_event import (
    MessageStatusEvent,
)
from app.db.models.outbox_event import (
    OutboxEvent,
)


class MessageStatusRepository:
    def __init__(
        self,
        *,
        session: AsyncSession,
        tenant_id: UUID,
    ) -> None:
        self._session = session
        self._tenant_id = tenant_id

    @property
    def tenant_id(self) -> UUID:
        return self._tenant_id

    async def get_outbound_message_for_update(
        self,
        meta_message_id: str,
    ) -> Message | None:
        statement: Select[Message] = (
            select(Message)
            .where(
                Message.tenant_id == self._tenant_id,
                Message.meta_message_id == meta_message_id,
                Message.direction == MessageDirection.OUTBOUND,
            )
            .with_for_update()
        )

        result = await self._session.scalars(statement)

        return result.first()

    def add_status_history(
        self,
        *,
        message_id: UUID,
        status: MessageStatus,
        meta_timestamp: datetime | None,
    ) -> MessageStatusEvent:
        event = MessageStatusEvent(
            tenant_id=self._tenant_id,
            message_id=message_id,
            status=status,
            meta_timestamp=meta_timestamp,
        )

        self._session.add(event)

        return event

    def set_effective_status(
        self,
        *,
        message: Message,
        status: MessageStatus,
    ) -> None:
        message.status = status

    def add_status_outbox_event(
        self,
        *,
        message: Message,
        status: MessageStatus,
    ) -> OutboxEvent:
        event_type = f"message.{status.value}"

        event = OutboxEvent(
            tenant_id=self._tenant_id,
            event_type=event_type,
            aggregate_type="message",
            aggregate_id=str(message.id),
            payload_json={
                "message_id": str(message.id),
                "conversation_id": str(message.conversation_id),
                "status": status.value,
            },
        )

        self._session.add(event)

        return event
