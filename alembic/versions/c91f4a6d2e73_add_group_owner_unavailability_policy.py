"""add group owner unavailability policy

Revision ID: c91f4a6d2e73
Revises: b7d2e4c93f10
Create Date: 2026-10-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c91f4a6d2e73"
down_revision: str | None = "b7d2e4c93f10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


owner_unavailable_policy = postgresql.ENUM(
    "keep_owner",
    "return_to_queue",
    "auto_reassign",
    "notify_admin",
    name="owner_unavailable_policy",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()

    owner_unavailable_policy.create(
        bind,
        checkfirst=True,
    )

    op.add_column(
        "groups",
        sa.Column(
            "owner_unavailable_policy",
            owner_unavailable_policy,
            nullable=False,
            server_default="keep_owner",
        ),
    )

    op.add_column(
        "groups",
        sa.Column(
            "offline_grace_seconds",
            sa.Integer(),
            nullable=False,
            server_default="300",
        ),
    )

    op.create_check_constraint(
        "ck_groups_offline_grace_seconds_non_negative",
        "groups",
        "offline_grace_seconds >= 0",
    )


def downgrade() -> None:
    bind = op.get_bind()

    op.drop_constraint(
        "ck_groups_offline_grace_seconds_non_negative",
        "groups",
        type_="check",
    )

    op.drop_column(
        "groups",
        "offline_grace_seconds",
    )

    op.drop_column(
        "groups",
        "owner_unavailable_policy",
    )

    owner_unavailable_policy.drop(
        bind,
        checkfirst=True,
    )
