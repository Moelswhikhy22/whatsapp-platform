from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    UniqueConstraint,
    func,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WhatsAppNumberGroup(Base):
    __tablename__ = "whatsapp_number_groups"

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_whatsapp_number_groups_tenant_id_id",
        ),
        UniqueConstraint(
            "tenant_id",
            "whatsapp_number_id",
            "group_id",
            name=("uq_whatsapp_number_groups_tenant_id_whatsapp_number_id_group_id"),
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
            name="fk_whatsapp_number_groups_tenant_number",
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
            name="fk_whatsapp_number_groups_tenant_group",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_whatsapp_number_groups_tenant_id_group_id",
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

    group_id: Mapped[UUID] = mapped_column(
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
