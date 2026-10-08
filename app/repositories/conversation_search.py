from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    String,
    and_,
    cast,
    exists,
    false,
    or_,
    select,
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
from app.db.models.group import Group
from app.db.models.message import Message
from app.db.models.whatsapp_number import (
    WhatsAppNumber,
)
from app.repositories.base import (
    TenantScopedRepository,
)


@dataclass(frozen=True, slots=True)
class ConversationSearchFilters:
    search: str | None = None

    conversation_id: UUID | None = None

    customer: str | None = None
    company: str | None = None
    phone: str | None = None

    whatsapp_number: str | None = None

    responsible_employee_id: UUID | None = None
    group_id: UUID | None = None

    state: ConversationState | None = None

    created_from: datetime | None = None
    created_to: datetime | None = None

    message_text: str | None = None


@dataclass(frozen=True, slots=True)
class ConversationSearchItem:
    id: UUID
    state: ConversationState

    customer_contact_id: UUID
    customer_name: str | None

    customer_company_id: UUID
    company_name: str

    phone_number: str

    whatsapp_number_id: UUID
    whatsapp_number: str

    group_id: UUID | None
    group_name: str | None

    responsible_employee_id: UUID | None

    created_at: datetime
    updated_at: datetime


class ConversationSearchRepository(TenantScopedRepository):
    async def search(
        self,
        *,
        filters: ConversationSearchFilters,
        allowed_group_ids: (frozenset[UUID] | None),
        limit: int,
        offset: int,
    ) -> list[ConversationSearchItem]:
        statement = (
            select(
                Conversation.id,
                Conversation.state,
                CustomerContact.id,
                CustomerContact.display_name,
                CustomerCompany.id,
                CustomerCompany.name,
                CustomerContact.phone_number,
                WhatsAppNumber.id,
                WhatsAppNumber.display_phone_number,
                Conversation.group_id,
                Group.name,
                Conversation.responsible_employee_id,
                Conversation.created_at,
                Conversation.updated_at,
            )
            .join(
                CustomerContact,
                and_(
                    CustomerContact.tenant_id == Conversation.tenant_id,
                    CustomerContact.id == Conversation.customer_contact_id,
                ),
            )
            .join(
                CustomerCompany,
                and_(
                    CustomerCompany.tenant_id == CustomerContact.tenant_id,
                    CustomerCompany.id == CustomerContact.customer_company_id,
                ),
            )
            .join(
                WhatsAppNumber,
                and_(
                    WhatsAppNumber.tenant_id == Conversation.tenant_id,
                    WhatsAppNumber.id == Conversation.whatsapp_number_id,
                ),
            )
            .outerjoin(
                Group,
                and_(
                    Group.tenant_id == Conversation.tenant_id,
                    Group.id == Conversation.group_id,
                ),
            )
        )

        statement = self._scope(
            statement,
            Conversation.tenant_id,
        )

        if allowed_group_ids is not None:
            if not allowed_group_ids:
                statement = statement.where(false())
            else:
                statement = statement.where(Conversation.group_id.in_(allowed_group_ids))

        if filters.conversation_id is not None:
            statement = statement.where(Conversation.id == filters.conversation_id)

        if filters.customer:
            statement = statement.where(
                CustomerContact.display_name.ilike(self._contains(filters.customer))
            )

        if filters.company:
            statement = statement.where(CustomerCompany.name.ilike(self._contains(filters.company)))

        if filters.phone:
            pattern = self._contains(filters.phone)

            statement = statement.where(
                or_(
                    CustomerContact.phone_number.ilike(pattern),
                    CustomerContact.normalized_phone.ilike(pattern),
                )
            )

        if filters.whatsapp_number:
            pattern = self._contains(filters.whatsapp_number)

            statement = statement.where(
                or_(
                    WhatsAppNumber.display_phone_number.ilike(pattern),
                    WhatsAppNumber.meta_phone_number_id.ilike(pattern),
                )
            )

        if filters.responsible_employee_id is not None:
            statement = statement.where(
                Conversation.responsible_employee_id == filters.responsible_employee_id
            )

        if filters.group_id is not None:
            statement = statement.where(Conversation.group_id == filters.group_id)

        if filters.state is not None:
            statement = statement.where(Conversation.state == filters.state)

        if filters.created_from is not None:
            statement = statement.where(Conversation.created_at >= filters.created_from)

        if filters.created_to is not None:
            statement = statement.where(Conversation.created_at <= filters.created_to)

        if filters.message_text:
            pattern = self._contains(filters.message_text)

            statement = statement.where(
                exists(
                    select(Message.id).where(
                        Message.tenant_id == self.tenant_id,
                        Message.conversation_id == Conversation.id,
                        Message.body_text.ilike(pattern),
                    )
                )
            )

        if filters.search:
            statement = statement.where(self._general_search_predicate(filters.search))

        statement = (
            statement.order_by(
                Conversation.updated_at.desc(),
                Conversation.id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )

        result = await self._session.execute(statement)

        return [
            ConversationSearchItem(
                id=row[0],
                state=row[1],
                customer_contact_id=row[2],
                customer_name=row[3],
                customer_company_id=row[4],
                company_name=row[5],
                phone_number=row[6],
                whatsapp_number_id=row[7],
                whatsapp_number=row[8],
                group_id=row[9],
                group_name=row[10],
                responsible_employee_id=row[11],
                created_at=row[12],
                updated_at=row[13],
            )
            for row in result.all()
        ]

    def _general_search_predicate(
        self,
        value: str,
    ):
        normalized = value.strip()

        pattern = self._contains(normalized)

        predicates = [
            cast(
                Conversation.id,
                String,
            ).ilike(pattern),
            CustomerContact.display_name.ilike(pattern),
            CustomerContact.phone_number.ilike(pattern),
            CustomerContact.normalized_phone.ilike(pattern),
            CustomerCompany.name.ilike(pattern),
            WhatsAppNumber.display_phone_number.ilike(pattern),
            WhatsAppNumber.meta_phone_number_id.ilike(pattern),
            Group.name.ilike(pattern),
        ]

        try:
            possible_uuid = UUID(normalized)
        except ValueError:
            possible_uuid = None

        if possible_uuid is not None:
            predicates.extend(
                [
                    Conversation.id == possible_uuid,
                    Conversation.responsible_employee_id == possible_uuid,
                    Conversation.group_id == possible_uuid,
                ]
            )

        return or_(*predicates)

    @staticmethod
    def _contains(
        value: str,
    ) -> str:
        escaped = value.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

        return f"%{escaped}%"
