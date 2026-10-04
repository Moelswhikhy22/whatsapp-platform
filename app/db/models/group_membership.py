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
    false,
    func,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class GroupMembership(Base):
    __tablename__ = "group_memberships"

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_group_memberships_tenant_id_id",
        ),
        UniqueConstraint(
            "tenant_id",
            "group_id",
            "employee_id",
            name="uq_group_memberships_tenant_id_group_id_employee_id",
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
            name="fk_group_memberships_tenant_group",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            [
                "tenant_id",
                "employee_id",
            ],
            [
                "employees.tenant_id",
                "employees.id",
            ],
            name="fk_group_memberships_tenant_employee",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_group_memberships_tenant_id_employee_id",
            "tenant_id",
            "employee_id",
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

    group_id: Mapped[UUID] = mapped_column(
        nullable=False,
    )

    employee_id: Mapped[UUID] = mapped_column(
        nullable=False,
    )

    is_admin: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=false(),
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
