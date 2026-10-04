from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
    text,
    true,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class IntegrationProvider(StrEnum):
    META = "meta"
    ODOO = "odoo"


integration_provider_type = Enum(
    IntegrationProvider,
    name="integration_provider",
    values_callable=lambda enum_type: [member.value for member in enum_type],
    validate_strings=True,
)


class Integration(Base):
    __tablename__ = "integrations"

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_integrations_tenant_id_id",
        ),
        UniqueConstraint(
            "tenant_id",
            "provider",
            "name",
            name="uq_integrations_tenant_id_provider_name",
        ),
        UniqueConstraint(
            "tenant_id",
            "provider",
            "external_account_id",
            name=("uq_integrations_tenant_id_provider_external_account_id"),
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

    provider: Mapped[IntegrationProvider] = mapped_column(
        integration_provider_type,
        nullable=False,
    )

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    external_account_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    config_json: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )

    vault_secret_reference: Mapped[str | None] = mapped_column(
        String(1024),
        nullable=True,
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
