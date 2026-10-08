from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Select,
    and_,
    func,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import (
    insert as pg_insert,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.conversation import (
    Conversation,
    ConversationState,
)
from app.db.models.customer_company import (
    CustomerCompany,
)
from app.db.models.customer_contact import (
    CustomerContact,
)
from app.db.models.employee import Employee
from app.db.models.group_membership import (
    GroupMembership,
)
from app.db.models.message import (
    ActorAttribution,
    Message,
    MessageDirection,
    MessageSource,
    MessageStatus,
    MessageType,
)
from app.db.models.outbox_event import OutboxEvent
from app.db.models.whatsapp_number import (
    WhatsAppNumber,
)
from app.db.models.whatsapp_number_group import (
    WhatsAppNumberGroup,
)


class IncomingMessageRepository:
    """
    Worker repository.

    Every business-data query is explicitly scoped by the trusted tenant_id
    resolved from RawWebhookEvent, rather than from message payload input.
    """

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

    async def get_active_whatsapp_number(
        self,
        meta_phone_number_id: str,
    ) -> WhatsAppNumber | None:
        statement: Select[WhatsAppNumber] = select(WhatsAppNumber).where(
            WhatsAppNumber.tenant_id == self._tenant_id,
            WhatsAppNumber.meta_phone_number_id == meta_phone_number_id,
            WhatsAppNumber.active.is_(True),
        )

        result = await self._session.scalars(statement)

        return result.first()

    async def get_contact_by_normalized_phone(
        self,
        normalized_phone: str,
    ) -> CustomerContact | None:
        statement: Select[CustomerContact] = select(CustomerContact).where(
            CustomerContact.tenant_id == self._tenant_id,
            CustomerContact.normalized_phone == normalized_phone,
        )

        result = await self._session.scalars(statement)

        return result.first()

    async def customer_company_is_active(
        self,
        customer_company_id: UUID,
    ) -> bool:
        statement = select(CustomerCompany.id).where(
            CustomerCompany.tenant_id == self._tenant_id,
            CustomerCompany.id == customer_company_id,
            CustomerCompany.active.is_(True),
        )

        result = await self._session.scalar(statement)

        return result is not None

    async def get_or_create_contact(
        self,
        *,
        customer_company_id: UUID,
        display_name: str | None,
        phone_number: str,
        normalized_phone: str,
    ) -> CustomerContact:
        contact_id = uuid4()

        statement = (
            pg_insert(CustomerContact)
            .values(
                id=contact_id,
                tenant_id=self._tenant_id,
                customer_company_id=customer_company_id,
                display_name=display_name,
                phone_number=phone_number,
                normalized_phone=normalized_phone,
                active=True,
            )
            .on_conflict_do_nothing(constraint=("uq_customer_contacts_tenant_id_normalized_phone"))
            .returning(CustomerContact.id)
        )

        await self._session.execute(statement)

        contact = await self.get_contact_by_normalized_phone(normalized_phone)

        if contact is None:
            raise RuntimeError("Customer contact could not be resolved.")

        return contact

    async def list_active_group_ids_for_number(
        self,
        whatsapp_number_id: UUID,
    ) -> list[UUID]:
        statement = (
            select(WhatsAppNumberGroup.group_id)
            .where(
                WhatsAppNumberGroup.tenant_id == self._tenant_id,
                WhatsAppNumberGroup.whatsapp_number_id == whatsapp_number_id,
                WhatsAppNumberGroup.active.is_(True),
            )
            .order_by(WhatsAppNumberGroup.group_id.asc())
        )

        result = await self._session.scalars(statement)

        return list(result.all())

    async def get_conversation(
        self,
        *,
        whatsapp_number_id: UUID,
        customer_contact_id: UUID,
    ) -> Conversation | None:
        statement: Select[Conversation] = select(Conversation).where(
            Conversation.tenant_id == self._tenant_id,
            Conversation.whatsapp_number_id == whatsapp_number_id,
            Conversation.customer_contact_id == customer_contact_id,
        )

        result = await self._session.scalars(statement)

        return result.first()

    async def get_or_create_conversation(
        self,
        *,
        whatsapp_number_id: UUID,
        customer_contact_id: UUID,
        group_id: UUID,
    ) -> tuple[Conversation, bool]:
        conversation_id = uuid4()

        statement = (
            pg_insert(Conversation)
            .values(
                id=conversation_id,
                tenant_id=self._tenant_id,
                whatsapp_number_id=whatsapp_number_id,
                customer_contact_id=customer_contact_id,
                group_id=group_id,
                state=ConversationState.QUEUED,
                responsible_employee_id=None,
                claimed_at=None,
            )
            .on_conflict_do_nothing(constraint=("uq_conversations_tenant_number_contact"))
            .returning(Conversation.id)
        )

        created_id = (await self._session.execute(statement)).scalar_one_or_none()

        conversation = await self.get_conversation(
            whatsapp_number_id=whatsapp_number_id,
            customer_contact_id=customer_contact_id,
        )

        if conversation is None:
            raise RuntimeError("Conversation could not be resolved.")

        return (
            conversation,
            created_id is not None,
        )

    async def assign_group_if_missing(
        self,
        *,
        conversation_id: UUID,
        group_id: UUID,
    ) -> Conversation:
        statement = (
            update(Conversation)
            .where(
                Conversation.tenant_id == self._tenant_id,
                Conversation.id == conversation_id,
                Conversation.group_id.is_(None),
            )
            .values(
                group_id=group_id,
                updated_at=func.now(),
            )
            .returning(Conversation)
        )

        result = await self._session.scalars(statement)

        updated = result.first()

        if updated is not None:
            return updated

        current = await self.get_conversation_by_id(conversation_id)

        if current is None:
            raise RuntimeError("Conversation disappeared during group resolution.")

        return current

    async def get_conversation_by_id(
        self,
        conversation_id: UUID,
    ) -> Conversation | None:
        statement: Select[Conversation] = select(Conversation).where(
            Conversation.tenant_id == self._tenant_id,
            Conversation.id == conversation_id,
        )

        result = await self._session.scalars(statement)

        return result.first()

    async def reopen_if_closed(
        self,
        conversation_id: UUID,
    ) -> Conversation | None:
        statement = (
            update(Conversation)
            .where(
                Conversation.tenant_id == self._tenant_id,
                Conversation.id == conversation_id,
                Conversation.state == ConversationState.CLOSED,
            )
            .values(
                state=ConversationState.REOPENED,
                updated_at=func.now(),
            )
            .returning(Conversation)
        )

        result = await self._session.scalars(statement)

        return result.first()

    async def insert_message_if_new(
        self,
        *,
        conversation_id: UUID,
        meta_message_id: str,
        message_type: MessageType,
        body_text: str | None,
        external_actor_id: str,
        meta_timestamp: datetime | None,
    ) -> UUID | None:
        message_id = uuid4()

        statement = (
            pg_insert(Message)
            .values(
                id=message_id,
                tenant_id=self._tenant_id,
                conversation_id=conversation_id,
                meta_message_id=meta_message_id,
                direction=MessageDirection.INBOUND,
                source=MessageSource.META,
                message_type=message_type,
                body_text=body_text,
                actual_actor_id=None,
                represented_employee_id=None,
                external_actor_id=external_actor_id,
                actor_attribution=(ActorAttribution.EXTERNAL),
                status=None,
                meta_timestamp=meta_timestamp,
            )
            .on_conflict_do_nothing(constraint=("uq_messages_tenant_id_meta_message_id"))
            .returning(Message.id)
        )

        result = await self._session.execute(statement)

        return result.scalar_one_or_none()

    async def insert_external_message_if_new(
        self,
        *,
        conversation_id: UUID,
        meta_message_id: str,
        message_type: MessageType,
        body_text: str | None,
        meta_timestamp: datetime | None,
    ) -> UUID | None:
        message_id = uuid4()

        statement = (
            pg_insert(Message)
            .values(
                id=message_id,
                tenant_id=self._tenant_id,
                conversation_id=conversation_id,
                meta_message_id=meta_message_id,
                direction=MessageDirection.OUTBOUND,
                source=MessageSource.WHATSAPP_EXTERNAL,
                message_type=message_type,
                body_text=body_text,
                actual_actor_id=None,
                represented_employee_id=None,
                external_actor_id=None,
                actor_attribution=ActorAttribution.UNKNOWN,
                status=MessageStatus.SENT,
                meta_timestamp=meta_timestamp,
            )
            .on_conflict_do_nothing(constraint=("uq_messages_tenant_id_meta_message_id"))
            .returning(Message.id)
        )

        result = await self._session.execute(statement)

        return result.scalar_one_or_none()

    async def list_eligible_team_member_ids(
        self,
        group_id: UUID,
    ) -> list[UUID]:
        statement = (
            select(Employee.id)
            .join(
                GroupMembership,
                and_(
                    GroupMembership.tenant_id == Employee.tenant_id,
                    GroupMembership.employee_id == Employee.id,
                ),
            )
            .where(
                Employee.tenant_id == self._tenant_id,
                GroupMembership.group_id == group_id,
                GroupMembership.active.is_(True),
                Employee.active.is_(True),
            )
            .order_by(Employee.id.asc())
        )

        result = await self._session.scalars(statement)

        return list(result.all())

    def add_outbox_event(
        self,
        *,
        event_type: str,
        aggregate_type: str,
        aggregate_id: str,
        payload_json: dict[str, object],
    ) -> OutboxEvent:
        event = OutboxEvent(
            tenant_id=self._tenant_id,
            event_type=event_type,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            payload_json=payload_json,
        )

        self._session.add(event)

        return event
