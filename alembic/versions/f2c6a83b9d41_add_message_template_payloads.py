"""add message template payloads

Revision ID: f2c6a83b9d41
Revises: a8d471c39e20
Create Date: 2026-10-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "f2c6a83b9d41"

down_revision: str | None = "a8d471c39e20"

branch_labels: str | Sequence[str] | None = None

depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "message_template_payloads",
        sa.Column(
            "id",
            sa.Uuid(),
            nullable=False,
        ),
        sa.Column(
            "tenant_id",
            sa.Uuid(),
            nullable=False,
        ),
        sa.Column(
            "message_id",
            sa.Uuid(),
            nullable=False,
        ),
        sa.Column(
            "template_id",
            sa.Uuid(),
            nullable=False,
        ),
        sa.Column(
            "components_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=("fk_message_template_payloads_tenant"),
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
            name=("fk_message_template_payloads_tenant_message"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            [
                "tenant_id",
                "template_id",
            ],
            [
                "templates.tenant_id",
                "templates.id",
            ],
            name=("fk_message_template_payloads_tenant_template"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name=("pk_message_template_payloads"),
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            name=("uq_message_template_payloads_tenant_id_id"),
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "message_id",
            name=("uq_message_template_payloads_tenant_message"),
        ),
    )

    op.create_index(
        ("ix_message_template_payloads_tenant_id"),
        "message_template_payloads",
        ["tenant_id"],
        unique=False,
    )

    op.create_index(
        ("ix_message_template_payloads_tenant_template"),
        "message_template_payloads",
        [
            "tenant_id",
            "template_id",
        ],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        ("ix_message_template_payloads_tenant_template"),
        table_name=("message_template_payloads"),
    )

    op.drop_index(
        ("ix_message_template_payloads_tenant_id"),
        table_name=("message_template_payloads"),
    )

    op.drop_table("message_template_payloads")
