from __future__ import annotations

from uuid import UUID

from sqlalchemy import (
    Select,
    select,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from app.db.models.conversation import (
    Conversation,
)
from app.db.models.integration import (
    Integration,
    IntegrationProvider,
)
from app.db.models.message import (
    Message,
    MessageDirection,
    MessageType,
)
from app.db.models.whatsapp_number import (
    WhatsAppNumber,
)


_MEDIA_TYPES = (
    MessageType.IMAGE,
    MessageType.DOCUMENT,
    MessageType.AUDIO,
    MessageType.VIDEO,
)


class MetaMediaRepository:
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

    async def get_inbound_media_message(
        self,
        message_id: UUID,
    ) -> Message | None:
        statement: Select[Message] = select(Message).where(
            Message.tenant_id == self._tenant_id,
            Message.id == message_id,
            Message.direction == MessageDirection.INBOUND,
            Message.message_type.in_(_MEDIA_TYPES),
        )

        result = await self._session.scalars(statement)

        return result.first()

    async def get_conversation(
        self,
        conversation_id: UUID,
    ) -> Conversation | None:
        statement: Select[Conversation] = select(Conversation).where(
            Conversation.tenant_id == self._tenant_id,
            Conversation.id == conversation_id,
        )

        result = await self._session.scalars(statement)

        return result.first()

    async def get_whatsapp_number(
        self,
        whatsapp_number_id: UUID,
    ) -> WhatsAppNumber | None:
        statement: Select[WhatsAppNumber] = select(WhatsAppNumber).where(
            WhatsAppNumber.tenant_id == self._tenant_id,
            WhatsAppNumber.id == whatsapp_number_id,
        )

        result = await self._session.scalars(statement)

        return result.first()

    async def get_meta_integration(
        self,
        integration_id: UUID,
    ) -> Integration | None:
        statement: Select[Integration] = select(Integration).where(
            Integration.tenant_id == self._tenant_id,
            Integration.id == integration_id,
            Integration.provider == IntegrationProvider.META,
        )

        result = await self._session.scalars(statement)

        return result.first()
