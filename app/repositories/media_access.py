from __future__ import annotations

from uuid import UUID

from sqlalchemy import Select, select

from app.db.models.conversation import Conversation
from app.db.models.group import Group
from app.db.models.media_object import MediaObject
from app.db.models.message import Message
from app.repositories.base import TenantScopedRepository


class MediaAccessRepository(TenantScopedRepository):
    async def get_media(
        self,
        *,
        message_id: UUID,
        media_id: UUID,
    ) -> MediaObject | None:
        statement: Select[MediaObject] = self._scope(
            select(MediaObject).where(
                MediaObject.id == media_id,
                MediaObject.message_id == message_id,
            ),
            MediaObject.tenant_id,
        )

        result = await self._session.scalars(statement)

        return result.first()

    async def get_message(
        self,
        message_id: UUID,
    ) -> Message | None:
        statement: Select[Message] = self._scope(
            select(Message).where(Message.id == message_id),
            Message.tenant_id,
        )

        result = await self._session.scalars(statement)

        return result.first()

    async def get_conversation(
        self,
        conversation_id: UUID,
    ) -> Conversation | None:
        statement: Select[Conversation] = self._scope(
            select(Conversation).where(Conversation.id == conversation_id),
            Conversation.tenant_id,
        )

        result = await self._session.scalars(statement)

        return result.first()

    async def get_group(
        self,
        group_id: UUID,
    ) -> Group | None:
        statement: Select[Group] = self._scope(
            select(Group).where(Group.id == group_id),
            Group.tenant_id,
        )

        result = await self._session.scalars(statement)

        return result.first()
