"""add group non-owner send policy

Revision ID: b7d2e4c93f10
Revises: a4f9c2d71b8e
Create Date: 2026-10-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7d2e4c93f10"
down_revision: str | None = "a4f9c2d71b8e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "groups",
        sa.Column(
            "allow_non_owner_employee_send",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column(
        "groups",
        "allow_non_owner_employee_send",
    )
