from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    UniqueConstraint,
    func,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WhatsAppNumber(Base):
    __tablename__ = "whatsapp_numbers"

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_whatsapp_numbers_tenant_id_id",
        ),
        UniqueConstraint(
            "meta_phone_number_id",
            name="uq_whatsapp_numbers_meta_phone_number_id",
        ),
        ForeignKeyConstraint(
            [
                "tenant_id",
                "integration_id",
            ],
            [
                "integrations.tenant_id",
                "integrations.id",
            ],
            name="fk_whatsapp_numbers_tenant_integration",
            ondelete="RESTRICT",
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

    integration_id: Mapped[UUID] = mapped_column(
        nullable=False,
    )

    meta_phone_number_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    display_phone_number: Mapped[str] = mapped_column(
        String(32),
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
