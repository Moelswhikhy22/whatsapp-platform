from __future__ import annotations

from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from app.db.models.conversation import (
    Conversation,
)
from app.db.models.customer_contact import (
    CustomerContact,
)
from app.db.models.integration import (
    Integration,
    IntegrationProvider,
)
from app.db.models.message import (
    Message,
    MessageDirection,
)
from app.db.models.message_template_payload import (
    MessageTemplatePayload,
)
from app.db.models.template import (
    Template,
    TemplateType,
)
from app.db.models.whatsapp_number import (
    WhatsAppNumber,
)


class MetaOutboundRepository:
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

    async def lock_outbound_message(
        self,
        message_id: UUID,
    ) -> Message | None:
        statement: Select[Message] = (
            select(Message)
            .where(
                Message.tenant_id == self._tenant_id,
                Message.id == message_id,
                Message.direction == MessageDirection.OUTBOUND,
            )
            .with_for_update()
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

    async def get_active_contact(
        self,
        contact_id: UUID,
    ) -> CustomerContact | None:
        statement: Select[CustomerContact] = select(CustomerContact).where(
            CustomerContact.tenant_id == self._tenant_id,
            CustomerContact.id == contact_id,
            CustomerContact.active.is_(True),
        )

        result = await self._session.scalars(statement)

        return result.first()

    async def get_active_whatsapp_number(
        self,
        whatsapp_number_id: UUID,
    ) -> WhatsAppNumber | None:
        statement: Select[WhatsAppNumber] = select(WhatsAppNumber).where(
            WhatsAppNumber.tenant_id == self._tenant_id,
            WhatsAppNumber.id == whatsapp_number_id,
            WhatsAppNumber.active.is_(True),
        )

        result = await self._session.scalars(statement)

        return result.first()

    async def get_active_meta_integration(
        self,
        integration_id: UUID,
    ) -> Integration | None:
        statement: Select[Integration] = select(Integration).where(
            Integration.tenant_id == self._tenant_id,
            Integration.id == integration_id,
            Integration.provider == IntegrationProvider.META,
            Integration.active.is_(True),
        )

        result = await self._session.scalars(statement)

        return result.first()

    async def get_template_payload(
        self,
        message_id: UUID,
    ) -> MessageTemplatePayload | None:
        statement: Select[MessageTemplatePayload] = select(MessageTemplatePayload).where(
            MessageTemplatePayload.tenant_id == self._tenant_id,
            MessageTemplatePayload.message_id == message_id,
        )

        result = await self._session.scalars(statement)

        return result.first()

    async def get_meta_template(
        self,
        template_id: UUID,
    ) -> Template | None:
        statement: Select[Template] = select(Template).where(
            Template.tenant_id == self._tenant_id,
            Template.id == template_id,
            Template.template_type == TemplateType.META,
        )

        result = await self._session.scalars(statement)

        return result.first()
