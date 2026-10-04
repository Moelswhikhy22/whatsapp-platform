from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
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


class MediaObject(Base):
    __tablename__ = "media_objects"

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_media_objects_tenant_id_id",
        ),
        UniqueConstraint(
            "bucket",
            "object_key",
            name="uq_media_objects_bucket_object_key",
        ),
        ForeignKeyConstraint(
            [
                "tenant_id",
                "message_id",
            ],
            [
                "messages.tenant_id",
                "messages.id",
            ],
            name="fk_media_objects_tenant_message",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "size_bytes >= 0",
            name="ck_media_objects_size_bytes_non_negative",
        ),
        Index(
            "ix_media_objects_tenant_id_message_id",
            "tenant_id",
            "message_id",
        ),
        Index(
            "ix_media_objects_tenant_id_retention_until",
            "tenant_id",
            "retention_until",
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

    message_id: Mapped[UUID] = mapped_column(
        nullable=False,
    )

    bucket: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    object_key: Mapped[str] = mapped_column(
        String(1024),
        nullable=False,
    )

    original_filename: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
    )

    mime_type: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    size_bytes: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    sha256: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    retention_until: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
