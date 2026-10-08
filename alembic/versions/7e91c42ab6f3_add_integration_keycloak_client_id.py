"""add integration keycloak client id

Revision ID: 7e91c42ab6f3
Revises: f2c6a83b9d41
Create Date: 2026-10-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "7e91c42ab6f3"

down_revision: str | None = "f2c6a83b9d41"

branch_labels: str | Sequence[str] | None = None

depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "integrations",
        sa.Column(
            "keycloak_client_id",
            sa.String(length=255),
            nullable=True,
        ),
    )

    op.create_unique_constraint(
        ("uq_integrations_keycloak_client_id"),
        "integrations",
        [
            "keycloak_client_id",
        ],
    )


def downgrade() -> None:
    op.drop_constraint(
        ("uq_integrations_keycloak_client_id"),
        "integrations",
        type_="unique",
    )

    op.drop_column(
        "integrations",
        "keycloak_client_id",
    )
