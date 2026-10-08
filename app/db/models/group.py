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
    Integer,
    UniqueConstraint,
    false,
    func,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OwnerUnavailablePolicy(StrEnum):
    KEEP_OWNER = "keep_owner"
    RETURN_TO_QUEUE = "return_to_queue"
    AUTO_REASSIGN = "auto_reassign"
    NOTIFY_ADMIN = "notify_admin"


owner_unavailable_policy_type = Enum(
    OwnerUnavailablePolicy,
    name="owner_unavailable_policy",
    values_callable=lambda enum_type: [member.value for member in enum_type],
    validate_strings=True,
)


class Group(Base):
    __tablename__ = "groups"

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_groups_tenant_id_id",
        ),
        UniqueConstraint(
            "tenant_id",
            "name",
            name="uq_groups_tenant_id_name",
        ),
        CheckConstraint(
            "offline_grace_seconds >= 0",
            name=("ck_groups_offline_grace_seconds_non_negative"),
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
        nullable=False,
    )

    claim_on_open: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=false(),
    )

    team_read_after_claim: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=false(),
    )

    allow_non_owner_employee_send: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=false(),
    )

    owner_unavailable_policy: Mapped[OwnerUnavailablePolicy] = mapped_column(
        owner_unavailable_policy_type,
        nullable=False,
        default=OwnerUnavailablePolicy.KEEP_OWNER,
        server_default=(OwnerUnavailablePolicy.KEEP_OWNER.value),
    )

    offline_grace_seconds: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=300,
        server_default="300",
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
