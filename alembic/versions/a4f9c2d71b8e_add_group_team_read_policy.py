"""add group team read policy

Revision ID: a4f9c2d71b8e
Revises: 715080a5d15c
Create Date: 2026-10-12
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a4f9c2d71b8e"
down_revision: str | None = "715080a5d15c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "groups",
        sa.Column(
            "team_read_after_claim",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column(
        "groups",
        "team_read_after_claim",
    )
