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


class RawWebhookProvider(StrEnum):
    META = "meta"


class RawWebhookProcessingStatus(StrEnum):
    RECEIVED = "received"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"
    UNRESOLVED = "unresolved"


raw_webhook_provider_type = Enum(
    RawWebhookProvider,
    name="raw_webhook_provider",
    values_callable=lambda enum_type: [member.value for member in enum_type],
    validate_strings=True,
)


raw_webhook_processing_status_type = Enum(
    RawWebhookProcessingStatus,
    name="raw_webhook_processing_status",
    values_callable=lambda enum_type: [member.value for member in enum_type],
    validate_strings=True,
)


class RawWebhookEvent(Base):
    __tablename__ = "raw_webhook_events"

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_raw_webhook_events_tenant_id_id",
        ),
        UniqueConstraint(
            "provider",
            "provider_event_key",
            name="uq_raw_webhook_events_provider_event_key",
        ),
        CheckConstraint(
            "attempts >= 0",
            name="ck_raw_webhook_events_attempts_non_negative",
        ),
        Index(
            "ix_raw_webhook_events_status_received_at",
            "processing_status",
            "received_at",
        ),
        Index(
            "ix_raw_webhook_events_tenant_status",
            "tenant_id",
            "processing_status",
        ),
        Index(
            "ix_raw_webhook_events_retention_until",
            "retention_until",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
    )

    tenant_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(
            "tenants.id",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )

    provider: Mapped[RawWebhookProvider] = mapped_column(
        raw_webhook_provider_type,
        nullable=False,
    )

    provider_event_key: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
    )

    event_type: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    payload_json: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
    )

    processing_status: Mapped[RawWebhookProcessingStatus] = mapped_column(
        raw_webhook_processing_status_type,
        nullable=False,
        default=RawWebhookProcessingStatus.RECEIVED,
        server_default=RawWebhookProcessingStatus.RECEIVED.value,
    )

    attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    last_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    retention_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
