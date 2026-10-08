from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OutboxEventStatus(StrEnum):
    PENDING = "pending"
    PUBLISHED = "published"
    FAILED = "failed"


outbox_event_status_type = Enum(
    OutboxEventStatus,
    name="outbox_event_status",
    values_callable=lambda enum_type: [member.value for member in enum_type],
    validate_strings=True,
)


class OutboxEvent(Base):
    __tablename__ = "outbox_events"

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_outbox_events_tenant_id_id",
        ),
        CheckConstraint(
            "attempts >= 0",
            name="ck_outbox_events_attempts_non_negative",
        ),
        CheckConstraint(
            """
            (
                status = 'published'
                AND published_at IS NOT NULL
            )
            OR
            (
                status <> 'published'
                AND published_at IS NULL
            )
            """,
            name="ck_outbox_events_published_state",
        ),
        Index(
            "ix_outbox_events_status_available_at_created_at",
            "status",
            "available_at",
            "created_at",
        ),
        Index(
            "ix_outbox_events_tenant_created_at",
            "tenant_id",
            "created_at",
        ),
        Index(
            "ix_outbox_events_tenant_aggregate",
            "tenant_id",
            "aggregate_type",
            "aggregate_id",
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

    event_type: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    aggregate_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    aggregate_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    payload_json: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
    )

    status: Mapped[OutboxEventStatus] = mapped_column(
        outbox_event_status_type,
        nullable=False,
        default=OutboxEventStatus.PENDING,
        server_default=OutboxEventStatus.PENDING.value,
    )

    attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    last_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
