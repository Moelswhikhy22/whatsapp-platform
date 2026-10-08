from __future__ import annotations

from datetime import datetime
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import (
    Select,
    func,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import (
    insert as pg_insert,
)

from app.db.models.conversation import (
    Conversation,
)
from app.db.models.group import Group
from app.db.models.message import (
    ActorAttribution,
    Message,
    MessageDirection,
    MessageSource,
    MessageStatus,
    MessageType,
)
from app.db.models.message_idempotency_key import (
    MessageIdempotencyKey,
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
from app.repositories.base import (
    TenantScopedRepository,
)


class OutboundMessageRepository(TenantScopedRepository):
    async def get_conversation(
        self,
        conversation_id: UUID,
    ) -> Conversation | None:
        statement: Select[Conversation] = self._scope(
            select(Conversation),
            Conversation.tenant_id,
        ).where(Conversation.id == conversation_id)

        result = await self._session.scalars(statement)

        return result.first()

    async def get_active_group(
        self,
        group_id: UUID,
    ) -> Group | None:
        statement: Select[Group] = self._scope(
            select(Group),
            Group.tenant_id,
        ).where(
            Group.id == group_id,
            Group.active.is_(True),
        )

        result = await self._session.scalars(statement)

        return result.first()

    async def get_active_whatsapp_number(
        self,
        whatsapp_number_id: UUID,
    ) -> WhatsAppNumber | None:
        statement: Select[WhatsAppNumber] = self._scope(
            select(WhatsAppNumber),
            WhatsAppNumber.tenant_id,
        ).where(
            WhatsAppNumber.id == whatsapp_number_id,
            WhatsAppNumber.active.is_(True),
        )

        result = await self._session.scalars(statement)

        return result.first()

    async def get_meta_template(
        self,
        template_id: UUID,
    ) -> Template | None:
        statement: Select[Template] = self._scope(
            select(Template),
            Template.tenant_id,
        ).where(
            Template.id == template_id,
            Template.template_type == TemplateType.META,
        )

        result = await self._session.scalars(statement)

        return result.first()

    async def last_customer_message_at(
        self,
        conversation_id: UUID,
    ) -> datetime | None:
        effective_timestamp = func.coalesce(
            Message.meta_timestamp,
            Message.created_at,
        )

        statement = (
            select(effective_timestamp)
            .where(
                Message.tenant_id == self.tenant_id,
                Message.conversation_id == conversation_id,
                Message.direction == MessageDirection.INBOUND,
            )
            .order_by(effective_timestamp.desc())
            .limit(1)
        )

        value = await self._session.scalar(statement)

        return cast(
            datetime | None,
            value,
        )

    async def try_claim_idempotency_key(
        self,
        *,
        actor_id: str,
        idempotency_key: str,
        request_hash: str,
    ) -> UUID | None:
        row_id = uuid4()

        statement = (
            pg_insert(MessageIdempotencyKey)
            .values(
                id=row_id,
                tenant_id=self.tenant_id,
                actor_id=actor_id,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                message_id=None,
            )
            .on_conflict_do_nothing(constraint=("uq_message_idempotency_keys_tenant_actor_key"))
            .returning(MessageIdempotencyKey.id)
        )

        result = await self._session.execute(statement)

        return result.scalar_one_or_none()

    async def get_idempotency_key(
        self,
        *,
        actor_id: str,
        idempotency_key: str,
    ) -> MessageIdempotencyKey | None:
        statement = self._scope(
            select(MessageIdempotencyKey),
            MessageIdempotencyKey.tenant_id,
        ).where(
            MessageIdempotencyKey.actor_id == actor_id,
            MessageIdempotencyKey.idempotency_key == idempotency_key,
        )

        result = await self._session.scalars(statement)

        return result.first()

    def add_pending_text_message(
        self,
        *,
        conversation_id: UUID,
        body_text: str,
        actual_actor_id: UUID | None,
    ) -> Message:
        message = Message(
            id=uuid4(),
            tenant_id=self.tenant_id,
            conversation_id=conversation_id,
            meta_message_id=None,
            direction=MessageDirection.OUTBOUND,
            source=MessageSource.PLATFORM,
            message_type=MessageType.TEXT,
            body_text=body_text,
            actual_actor_id=actual_actor_id,
            represented_employee_id=None,
            external_actor_id=None,
            actor_attribution=(
                ActorAttribution.EXACT if actual_actor_id is not None else ActorAttribution.UNKNOWN
            ),
            status=MessageStatus.PENDING,
            meta_timestamp=None,
        )

        self._session.add(message)

        return message

    def add_pending_template_message(
        self,
        *,
        conversation_id: UUID,
        template_id: UUID,
        components: list[dict[str, object]],
        actual_actor_id: UUID | None,
    ) -> Message:
        message = Message(
            id=uuid4(),
            tenant_id=self.tenant_id,
            conversation_id=conversation_id,
            meta_message_id=None,
            direction=MessageDirection.OUTBOUND,
            source=MessageSource.PLATFORM,
            message_type=MessageType.TEMPLATE,
            body_text=None,
            actual_actor_id=actual_actor_id,
            represented_employee_id=None,
            external_actor_id=None,
            actor_attribution=(
                ActorAttribution.EXACT if actual_actor_id is not None else ActorAttribution.UNKNOWN
            ),
            status=MessageStatus.PENDING,
            meta_timestamp=None,
        )

        payload = MessageTemplatePayload(
            id=uuid4(),
            tenant_id=self.tenant_id,
            message_id=message.id,
            template_id=template_id,
            components_json=[dict(component) for component in components],
        )

        self._session.add_all(
            [
                message,
                payload,
            ]
        )

        return message

    async def bind_idempotency_message(
        self,
        *,
        idempotency_row_id: UUID,
        message_id: UUID,
    ) -> None:
        statement = (
            update(MessageIdempotencyKey)
            .where(
                MessageIdempotencyKey.tenant_id == self.tenant_id,
                MessageIdempotencyKey.id == idempotency_row_id,
                MessageIdempotencyKey.message_id.is_(None),
            )
            .values(message_id=message_id)
        )

        await self._session.execute(statement)

    async def get_message(
        self,
        message_id: UUID,
    ) -> Message | None:
        statement: Select[Message] = self._scope(
            select(Message),
            Message.tenant_id,
        ).where(Message.id == message_id)

        result = await self._session.scalars(statement)

        return result.first()
