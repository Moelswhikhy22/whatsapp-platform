from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    func,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CustomerContact(Base):
    __tablename__ = "customer_contacts"

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_customer_contacts_tenant_id_id",
        ),
        UniqueConstraint(
            "tenant_id",
            "normalized_phone",
            name="uq_customer_contacts_tenant_id_normalized_phone",
        ),
        ForeignKeyConstraint(
            [
                "tenant_id",
                "customer_company_id",
            ],
            [
                "customer_companies.tenant_id",
                "customer_companies.id",
            ],
            name="fk_customer_contacts_tenant_company",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_customer_contacts_tenant_id_company_id",
            "tenant_id",
            "customer_company_id",
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

    customer_company_id: Mapped[UUID] = mapped_column(
        nullable=False,
    )

    display_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    phone_number: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    normalized_phone: Mapped[str] = mapped_column(
        String(32),
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
