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
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MessageDirection(StrEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class MessageType(StrEnum):
    TEXT = "text"
    IMAGE = "image"
    DOCUMENT = "document"
    AUDIO = "audio"
    VIDEO = "video"
    TEMPLATE = "template"


class MessageStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"


message_direction_type = Enum(
    MessageDirection,
    name="message_direction",
    values_callable=lambda enum_type: [member.value for member in enum_type],
    validate_strings=True,
)


message_type_type = Enum(
    MessageType,
    name="message_type",
    values_callable=lambda enum_type: [member.value for member in enum_type],
    validate_strings=True,
)


message_status_type = Enum(
    MessageStatus,
    name="message_status",
    values_callable=lambda enum_type: [member.value for member in enum_type],
    validate_strings=True,
)


class Message(Base):
    __tablename__ = "messages"

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_messages_tenant_id_id",
        ),
        UniqueConstraint(
            "tenant_id",
            "meta_message_id",
            name="uq_messages_tenant_id_meta_message_id",
        ),
        ForeignKeyConstraint(
            [
                "tenant_id",
                "conversation_id",
            ],
            [
                "conversations.tenant_id",
                "conversations.id",
            ],
            name="fk_messages_tenant_conversation",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            [
                "tenant_id",
                "actual_actor_id",
            ],
            [
                "employees.tenant_id",
                "employees.id",
            ],
            name="fk_messages_tenant_actual_actor",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            [
                "tenant_id",
                "represented_employee_id",
            ],
            [
                "employees.tenant_id",
                "employees.id",
            ],
            name="fk_messages_tenant_represented_employee",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_messages_tenant_id_conversation_created_at",
            "tenant_id",
            "conversation_id",
            "created_at",
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

    conversation_id: Mapped[UUID] = mapped_column(
        nullable=False,
    )

    meta_message_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    direction: Mapped[MessageDirection] = mapped_column(
        message_direction_type,
        nullable=False,
    )

    message_type: Mapped[MessageType] = mapped_column(
        message_type_type,
        nullable=False,
    )

    body_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    actual_actor_id: Mapped[UUID | None] = mapped_column(
        nullable=True,
    )

    represented_employee_id: Mapped[UUID | None] = mapped_column(
        nullable=True,
    )

    external_actor_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    status: Mapped[MessageStatus | None] = mapped_column(
        message_status_type,
        nullable=True,
    )

    meta_timestamp: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
