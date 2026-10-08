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
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SecurityPrincipalType(StrEnum):
    ANONYMOUS = "anonymous"
    HUMAN = "human"
    INTEGRATION = "integration"
    SYSTEM = "system"


class SecurityAccessOutcome(StrEnum):
    SUCCESS = "success"
    DENIED = "denied"
    FAILURE = "failure"


security_principal_type = Enum(
    SecurityPrincipalType,
    name="security_principal_type",
    values_callable=lambda enum_type: [member.value for member in enum_type],
    validate_strings=True,
)


security_access_outcome_type = Enum(
    SecurityAccessOutcome,
    name="security_access_outcome",
    values_callable=lambda enum_type: [member.value for member in enum_type],
    validate_strings=True,
)


class SecurityAccessLog(Base):
    __tablename__ = "security_access_logs"

    __table_args__ = (
        CheckConstraint(
            """
            (
                principal_type = 'anonymous'
                AND principal_id IS NULL
            )
            OR
            (
                principal_type <> 'anonymous'
                AND principal_id IS NOT NULL
            )
            """,
            name="ck_security_access_logs_principal_identity",
        ),
        Index(
            "ix_security_access_logs_created_at",
            "created_at",
        ),
        Index(
            "ix_security_access_logs_tenant_created_at",
            "tenant_id",
            "created_at",
        ),
        Index(
            "ix_security_access_logs_event_outcome_created_at",
            "event",
            "outcome",
            "created_at",
        ),
        Index(
            "ix_security_access_logs_principal_created_at",
            "principal_type",
            "principal_id",
            "created_at",
        ),
        Index(
            "ix_security_access_logs_trace_id",
            "trace_id",
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

    principal_type: Mapped[SecurityPrincipalType] = mapped_column(
        security_principal_type,
        nullable=False,
    )

    principal_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    event: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    outcome: Mapped[SecurityAccessOutcome] = mapped_column(
        security_access_outcome_type,
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

    request_method: Mapped[str | None] = mapped_column(
        String(16),
        nullable=True,
    )

    request_path: Mapped[str | None] = mapped_column(
        String(2048),
        nullable=True,
    )

    client_ip: Mapped[str | None] = mapped_column(
        String(45),
        nullable=True,
    )

    user_agent: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    reason_code: Mapped[str | None] = mapped_column(
        String(100),
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
