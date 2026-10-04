from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.message import (
    MessageStatus,
    message_status_type,
)


class MessageStatusEvent(Base):
    __tablename__ = "message_status_events"

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_message_status_events_tenant_id_id",
        ),
        ForeignKeyConstraint(
            [
                "tenant_id",
                "message_id",
            ],
            [
                "messages.tenant_id",
                "messages.id",
            ],
            name="fk_message_status_events_tenant_message",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_message_status_events_tenant_message_created_at",
            "tenant_id",
            "message_id",
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

    message_id: Mapped[UUID] = mapped_column(
        nullable=False,
    )

    status: Mapped[MessageStatus] = mapped_column(
        message_status_type,
        nullable=False,
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
