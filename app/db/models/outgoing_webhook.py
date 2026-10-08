from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    true,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OutgoingWebhookDeliveryStatus(StrEnum):
    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"


class OutgoingWebhookAttemptOutcome(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


outgoing_webhook_delivery_status_type = Enum(
    OutgoingWebhookDeliveryStatus,
    name="outgoing_webhook_delivery_status",
    values_callable=lambda enum_type: [member.value for member in enum_type],
    validate_strings=True,
)


outgoing_webhook_attempt_outcome_type = Enum(
    OutgoingWebhookAttemptOutcome,
    name="outgoing_webhook_attempt_outcome",
    values_callable=lambda enum_type: [member.value for member in enum_type],
    validate_strings=True,
)


class OutgoingWebhookSubscription(Base):
    __tablename__ = "outgoing_webhook_subscriptions"

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "id",
            name=("uq_outgoing_webhook_subscriptions_tenant_id_id"),
        ),
        UniqueConstraint(
            "tenant_id",
            "name",
            name=("uq_outgoing_webhook_subscriptions_tenant_name"),
        ),
        Index(
            "ix_outgoing_webhook_subscriptions_tenant_active",
            "tenant_id",
            "active",
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

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    endpoint_url: Mapped[str] = mapped_column(
        String(2048),
        nullable=False,
    )

    event_types_json: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
    )

    vault_secret_reference: Mapped[str] = mapped_column(
        String(1024),
        nullable=False,
    )

    active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=true(),
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


class OutgoingWebhookDelivery(Base):
    __tablename__ = "outgoing_webhook_deliveries"

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_outgoing_webhook_deliveries_tenant_id_id",
        ),
        UniqueConstraint(
            "tenant_id",
            "subscription_id",
            "event_id",
            name=("uq_outgoing_webhook_deliveries_tenant_subscription_event"),
        ),
        ForeignKeyConstraint(
            [
                "tenant_id",
                "subscription_id",
            ],
            [
                "outgoing_webhook_subscriptions.tenant_id",
                "outgoing_webhook_subscriptions.id",
            ],
            name=("fk_outgoing_webhook_deliveries_tenant_subscription"),
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "attempt_count >= 0",
            name=("ck_outgoing_webhook_deliveries_attempt_count_non_negative"),
        ),
        CheckConstraint(
            """
            last_http_status_code IS NULL
            OR (
                last_http_status_code >= 100
                AND last_http_status_code <= 599
            )
            """,
            name=("ck_outgoing_webhook_deliveries_http_status_code"),
        ),
        CheckConstraint(
            """
            (
                status = 'delivered'
                AND delivered_at IS NOT NULL
            )
            OR
            (
                status <> 'delivered'
                AND delivered_at IS NULL
            )
            """,
            name=("ck_outgoing_webhook_deliveries_delivered_state"),
        ),
        Index(
            "ix_outgoing_webhook_deliveries_status_next_attempt_created_at",
            "status",
            "next_attempt_at",
            "created_at",
        ),
        Index(
            "ix_outgoing_webhook_deliveries_tenant_subscription_created_at",
            "tenant_id",
            "subscription_id",
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

    subscription_id: Mapped[UUID] = mapped_column(
        nullable=False,
    )

    event_id: Mapped[UUID] = mapped_column(
        nullable=False,
    )

    event_type: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    payload_json: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
    )

    status: Mapped[OutgoingWebhookDeliveryStatus] = mapped_column(
        outgoing_webhook_delivery_status_type,
        nullable=False,
        default=OutgoingWebhookDeliveryStatus.PENDING,
        server_default=OutgoingWebhookDeliveryStatus.PENDING.value,
    )

    attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    last_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    last_http_status_code: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    last_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    delivered_at: Mapped[datetime | None] = mapped_column(
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


class OutgoingWebhookDeliveryAttempt(Base):
    __tablename__ = "outgoing_webhook_delivery_attempts"

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "id",
            name=("uq_outgoing_webhook_delivery_attempts_tenant_id_id"),
        ),
        UniqueConstraint(
            "tenant_id",
            "delivery_id",
            "attempt_number",
            name=("uq_outgoing_webhook_delivery_attempts_tenant_delivery_attempt"),
        ),
        ForeignKeyConstraint(
            [
                "tenant_id",
                "delivery_id",
            ],
            [
                "outgoing_webhook_deliveries.tenant_id",
                "outgoing_webhook_deliveries.id",
            ],
            name=("fk_outgoing_webhook_delivery_attempts_tenant_delivery"),
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "attempt_number > 0",
            name=("ck_outgoing_webhook_delivery_attempts_attempt_number_positive"),
        ),
        CheckConstraint(
            """
            http_status_code IS NULL
            OR (
                http_status_code >= 100
                AND http_status_code <= 599
            )
            """,
            name=("ck_outgoing_webhook_delivery_attempts_http_status_code"),
        ),
        Index(
            "ix_outgoing_webhook_attempts_tenant_delivery_attempted_at",
            "tenant_id",
            "delivery_id",
            "attempted_at",
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

    delivery_id: Mapped[UUID] = mapped_column(
        nullable=False,
    )

    attempt_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    outcome: Mapped[OutgoingWebhookAttemptOutcome] = mapped_column(
        outgoing_webhook_attempt_outcome_type,
        nullable=False,
    )

    http_status_code: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
