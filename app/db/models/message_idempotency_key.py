from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MessageIdempotencyKey(Base):
    __tablename__ = "message_idempotency_keys"

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "actor_id",
            "idempotency_key",
            name=("uq_message_idempotency_keys_tenant_actor_key"),
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
            name=("fk_message_idempotency_keys_tenant_message"),
            ondelete="CASCADE",
        ),
        Index(
            ("ix_message_idempotency_keys_tenant_actor"),
            "tenant_id",
            "actor_id",
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

    actor_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    idempotency_key: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    request_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    message_id: Mapped[UUID | None] = mapped_column(
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
