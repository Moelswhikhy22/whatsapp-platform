from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint, true
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TenantDomain(Base):
    __tablename__ = "tenant_domains"

    __table_args__ = (
        UniqueConstraint(
            "hostname",
            name="uq_tenant_domains_hostname",
        ),
        UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_tenant_domains_tenant_id_id",
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

    hostname: Mapped[str] = mapped_column(
        String(253),
        nullable=False,
    )

    active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=true(),
    )
