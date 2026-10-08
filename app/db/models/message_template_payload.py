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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MessageTemplatePayload(Base):
    __tablename__ = "message_template_payloads"

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "id",
            name=("uq_message_template_payloads_tenant_id_id"),
        ),
        UniqueConstraint(
            "tenant_id",
            "message_id",
            name=("uq_message_template_payloads_tenant_message"),
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
            name=("fk_message_template_payloads_tenant_message"),
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            [
                "tenant_id",
                "template_id",
            ],
            [
                "templates.tenant_id",
                "templates.id",
            ],
            name=("fk_message_template_payloads_tenant_template"),
            ondelete="RESTRICT",
        ),
        Index(
            ("ix_message_template_payloads_tenant_template"),
            "tenant_id",
            "template_id",
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

    template_id: Mapped[UUID] = mapped_column(
        nullable=False,
    )

    components_json: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
