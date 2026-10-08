from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.conversation import Conversation
from app.db.models.outbox_event import OutboxEvent
from app.repositories.conversation import ConversationRepository


class SharedInboxService:
    def __init__(
        self,
        session: AsyncSession,
        conversation_repository: ConversationRepository,
    ) -> None:
        self._session = session
        self._conversation_repository = conversation_repository

    async def notify_eligible_team_members(
        self,
        conversation: Conversation,
    ) -> OutboxEvent | None:
        if conversation.group_id is None:
            return None

        employee_ids = await self._conversation_repository.list_eligible_team_member_ids(
            conversation.group_id,
        )

        if not employee_ids:
            return None

        event = OutboxEvent(
            tenant_id=conversation.tenant_id,
            event_type="conversation.queued",
            aggregate_type="conversation",
            aggregate_id=str(conversation.id),
            payload_json={
                "conversation_id": str(conversation.id),
                "group_id": str(conversation.group_id),
                "recipient_employee_ids": [str(employee_id) for employee_id in employee_ids],
            },
        )

        self._session.add(event)
        await self._session.flush()

        return event
