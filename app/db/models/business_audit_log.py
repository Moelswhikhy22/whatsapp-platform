from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class BusinessAuditActorType(StrEnum):
    HUMAN = "human"
    INTEGRATION = "integration"
    SYSTEM = "system"


business_audit_actor_type = Enum(
    BusinessAuditActorType,
    name="business_audit_actor_type",
    values_callable=lambda enum_type: [member.value for member in enum_type],
    validate_strings=True,
)


class BusinessAuditLog(Base):
    __tablename__ = "business_audit_logs"

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_business_audit_logs_tenant_id_id",
        ),
        Index(
            "ix_business_audit_logs_tenant_created_at",
            "tenant_id",
            "created_at",
        ),
        Index(
            "ix_business_audit_logs_tenant_resource_created_at",
            "tenant_id",
            "resource_type",
            "resource_id",
            "created_at",
        ),
        Index(
            "ix_business_audit_logs_tenant_actor_created_at",
            "tenant_id",
            "actor_type",
            "actor_id",
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

    actor_type: Mapped[BusinessAuditActorType] = mapped_column(
        business_audit_actor_type,
        nullable=False,
    )

    actor_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    action: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    resource_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    resource_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    before_json: Mapped[dict[str, object] | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    after_json: Mapped[dict[str, object] | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    trace_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
