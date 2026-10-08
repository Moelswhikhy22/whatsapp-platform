from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ExternalIdentity(Base):
    __tablename__ = "external_identities"

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_external_identities_tenant_id_id",
        ),
        UniqueConstraint(
            "tenant_id",
            "provider",
            "external_user_id",
            name=("uq_external_identities_tenant_provider_external_user_id"),
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
            name="fk_external_identities_tenant_employee",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_external_identities_tenant_employee_id",
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

    provider: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    external_user_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    employee_id: Mapped[UUID] = mapped_column(
        nullable=False,
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
