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
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PlatformAuditActorType(StrEnum):
    HUMAN = "human"
    INTEGRATION = "integration"
    SYSTEM = "system"


platform_audit_actor_type = Enum(
    PlatformAuditActorType,
    name="platform_audit_actor_type",
    values_callable=lambda enum_type: [member.value for member in enum_type],
    validate_strings=True,
)


class PlatformAuditLog(Base):
    __tablename__ = "platform_audit_logs"

    __table_args__ = (
        Index(
            "ix_platform_audit_logs_created_at",
            "created_at",
        ),
        Index(
            "ix_platform_audit_logs_affected_tenant_created_at",
            "affected_tenant_id",
            "created_at",
        ),
        Index(
            "ix_platform_audit_logs_actor_created_at",
            "actor_type",
            "actor_id",
            "created_at",
        ),
        Index(
            "ix_platform_audit_logs_resource_created_at",
            "resource_type",
            "resource_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
    )

    affected_tenant_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(
            "tenants.id",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )

    actor_type: Mapped[PlatformAuditActorType] = mapped_column(
        platform_audit_actor_type,
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

    resource_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    resource_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
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
