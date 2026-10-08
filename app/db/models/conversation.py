from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ConversationState(StrEnum):
    QUEUED = "queued"
    CLAIMED = "claimed"
    OPEN = "open"
    WAITING_CUSTOMER = "waiting_customer"
    WAITING_TEAM = "waiting_team"
    CLOSED = "closed"
    REOPENED = "reopened"


conversation_state_type = Enum(
    ConversationState,
    name="conversation_state",
    values_callable=lambda enum_type: [member.value for member in enum_type],
    validate_strings=True,
)


class Conversation(Base):
    __tablename__ = "conversations"

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_conversations_tenant_id_id",
        ),
        UniqueConstraint(
            "tenant_id",
            "whatsapp_number_id",
            "customer_contact_id",
            name="uq_conversations_tenant_number_contact",
        ),
        ForeignKeyConstraint(
            [
                "tenant_id",
                "whatsapp_number_id",
            ],
            [
                "whatsapp_numbers.tenant_id",
                "whatsapp_numbers.id",
            ],
            name="fk_conversations_tenant_whatsapp_number",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            [
                "tenant_id",
                "customer_contact_id",
            ],
            [
                "customer_contacts.tenant_id",
                "customer_contacts.id",
            ],
            name="fk_conversations_tenant_customer_contact",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            [
                "tenant_id",
                "group_id",
            ],
            [
                "groups.tenant_id",
                "groups.id",
            ],
            name="fk_conversations_tenant_group",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            [
                "tenant_id",
                "responsible_employee_id",
            ],
            [
                "employees.tenant_id",
                "employees.id",
            ],
            name="fk_conversations_tenant_responsible_employee",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_conversations_tenant_id_customer_contact_id",
            "tenant_id",
            "customer_contact_id",
        ),
        Index(
            "ix_conversations_tenant_id_group_id",
            "tenant_id",
            "group_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
    )

    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "tenants.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    whatsapp_number_id: Mapped[UUID] = mapped_column(
        nullable=False,
    )

    customer_contact_id: Mapped[UUID] = mapped_column(
        nullable=False,
    )

    group_id: Mapped[UUID | None] = mapped_column(
        nullable=True,
    )

    state: Mapped[ConversationState] = mapped_column(
        conversation_state_type,
        nullable=False,
        default=ConversationState.QUEUED,
        server_default=ConversationState.QUEUED.value,
    )

    responsible_employee_id: Mapped[UUID | None] = mapped_column(
        nullable=True,
    )

    claimed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
