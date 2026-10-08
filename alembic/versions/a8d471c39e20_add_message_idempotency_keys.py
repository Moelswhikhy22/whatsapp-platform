"""add message idempotency keys

Revision ID: a8d471c39e20
Revises: 715080a5d15c
Create Date: 2026-10-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "a8d471c39e20"
down_revision: str | None = "c91f4a6d2e73"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "message_idempotency_keys",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "actor_id",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "idempotency_key",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "request_hash",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "message_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=("fk_message_idempotency_keys_tenant"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            [
                "tenant_id",
                "message_id",
            ],
            [
                "messages.tenant_id",
                "messages.id",
            ],
            name=("fk_message_idempotency_keys_tenant_message"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name=("pk_message_idempotency_keys"),
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "actor_id",
            "idempotency_key",
            name=("uq_message_idempotency_keys_tenant_actor_key"),
        ),
    )

    op.create_index(
        ("ix_message_idempotency_keys_tenant_id"),
        "message_idempotency_keys",
        ["tenant_id"],
        unique=False,
    )

    op.create_index(
        ("ix_message_idempotency_keys_tenant_actor"),
        "message_idempotency_keys",
        [
            "tenant_id",
            "actor_id",
        ],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        ("ix_message_idempotency_keys_tenant_actor"),
        table_name=("message_idempotency_keys"),
    )

    op.drop_index(
        ("ix_message_idempotency_keys_tenant_id"),
        table_name=("message_idempotency_keys"),
    )

    op.drop_table("message_idempotency_keys")
