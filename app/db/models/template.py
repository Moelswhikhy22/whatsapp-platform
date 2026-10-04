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
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TemplateType(StrEnum):
    INTERNAL = "internal"
    META = "meta"


class TemplateStatus(StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"
    PAUSED = "paused"
    DISABLED = "disabled"


template_type_type = Enum(
    TemplateType,
    name="template_type",
    values_callable=lambda enum_type: [member.value for member in enum_type],
    validate_strings=True,
)


template_status_type = Enum(
    TemplateStatus,
    name="template_status",
    values_callable=lambda enum_type: [member.value for member in enum_type],
    validate_strings=True,
)


class Template(Base):
    __tablename__ = "templates"

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_templates_tenant_id_id",
        ),
        UniqueConstraint(
            "tenant_id",
            "name",
            name="uq_templates_tenant_internal_name",
        ),
        UniqueConstraint(
            "tenant_id",
            "meta_account_id",
            "meta_template_name",
            "language",
            name="uq_templates_tenant_meta_account_name_language",
        ),
        ForeignKeyConstraint(
            [
                "tenant_id",
                "meta_account_id",
            ],
            [
                "integrations.tenant_id",
                "integrations.id",
            ],
            name="fk_templates_tenant_meta_account",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            """
            (
                template_type = 'internal'
                AND name IS NOT NULL
                AND body IS NOT NULL
                AND variables_json IS NOT NULL
                AND active IS NOT NULL
                AND meta_template_name IS NULL
                AND language IS NULL
                AND components_json IS NULL
                AND status IS NULL
                AND meta_account_id IS NULL
                AND last_synced_at IS NULL
            )
            OR
            (
                template_type = 'meta'
                AND name IS NULL
                AND body IS NULL
                AND variables_json IS NULL
                AND active IS NULL
                AND meta_template_name IS NOT NULL
                AND language IS NOT NULL
                AND components_json IS NOT NULL
                AND status IS NOT NULL
                AND meta_account_id IS NOT NULL
            )
            """,
            name="ck_templates_type_specific_shape",
        ),
        Index(
            "ix_templates_tenant_id_template_type",
            "tenant_id",
            "template_type",
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

    template_type: Mapped[TemplateType] = mapped_column(
        template_type_type,
        nullable=False,
    )

    category: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    body: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    variables_json: Mapped[list[object] | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    active: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )

    meta_template_name: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
    )

    language: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
    )

    components_json: Mapped[list[dict[str, object]] | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    status: Mapped[TemplateStatus | None] = mapped_column(
        template_status_type,
        nullable=True,
    )

    meta_account_id: Mapped[UUID | None] = mapped_column(
        nullable=True,
    )

    last_synced_at: Mapped[datetime | None] = mapped_column(
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
