from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ConversationAssignmentReason(StrEnum):
    CLAIM = "claim"
    REASSIGNMENT = "reassignment"
    RETURN_TO_QUEUE = "return_to_queue"
    AUTO_REASSIGNMENT = "auto_reassignment"


conversation_assignment_reason_type = Enum(
    ConversationAssignmentReason,
    name="conversation_assignment_reason",
    values_callable=lambda enum_type: [member.value for member in enum_type],
    validate_strings=True,
)


class ConversationAssignmentHistory(Base):
    __tablename__ = "conversation_assignment_history"

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "id",
            name=("uq_conversation_assignment_history_tenant_id_id"),
        ),
        ForeignKeyConstraint(
            [
                "tenant_id",
                "conversation_id",
            ],
            [
                "conversations.tenant_id",
                "conversations.id",
            ],
            name=("fk_conversation_assignment_history_tenant_conversation"),
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            [
                "tenant_id",
                "previous_employee_id",
            ],
            [
                "employees.tenant_id",
                "employees.id",
            ],
            name=("fk_conversation_assignment_history_tenant_previous_employee"),
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            [
                "tenant_id",
                "new_employee_id",
            ],
            [
                "employees.tenant_id",
                "employees.id",
            ],
            name=("fk_conversation_assignment_history_tenant_new_employee"),
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            ("previous_employee_id IS DISTINCT FROM new_employee_id"),
            name=("ck_conversation_assignment_history_employee_changed"),
        ),
        Index(
            "ix_conversation_assignment_history_tenant_conversation_created_at",
            "tenant_id",
            "conversation_id",
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

    conversation_id: Mapped[UUID] = mapped_column(
        nullable=False,
    )

    previous_employee_id: Mapped[UUID | None] = mapped_column(
        nullable=True,
    )

    new_employee_id: Mapped[UUID | None] = mapped_column(
        nullable=True,
    )

    reason: Mapped[ConversationAssignmentReason] = mapped_column(
        conversation_assignment_reason_type,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
