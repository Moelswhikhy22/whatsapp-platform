"""add message source attribution

Revision ID: c7b1a4d92e63
Revises: 7e91c42ab6f3
Create Date: 2026-10-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "c7b1a4d92e63"

down_revision: str | None = "7e91c42ab6f3"

branch_labels: str | Sequence[str] | None = None

depends_on: str | Sequence[str] | None = None


message_source = postgresql.ENUM(
    "meta",
    "platform",
    "odoo",
    "integration",
    "whatsapp_external",
    "unknown",
    name="message_source",
    create_type=False,
)


actor_attribution = postgresql.ENUM(
    "exact",
    "represented",
    "external",
    "unknown",
    name="actor_attribution",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()

    message_source.create(
        bind,
        checkfirst=True,
    )

    actor_attribution.create(
        bind,
        checkfirst=True,
    )

    op.add_column(
        "messages",
        sa.Column(
            "source",
            message_source,
            nullable=True,
        ),
    )

    op.add_column(
        "messages",
        sa.Column(
            "actor_attribution",
            actor_attribution,
            nullable=True,
        ),
    )

    op.execute(
        """
        UPDATE messages
        SET source =
            CASE
                WHEN direction = 'inbound'
                    THEN 'meta'::message_source

                WHEN direction = 'outbound'
                    THEN 'platform'::message_source

                ELSE 'unknown'::message_source
            END
        """
    )

    op.execute(
        """
        UPDATE messages
        SET actor_attribution =
            CASE
                WHEN represented_employee_id
                     IS NOT NULL
                    THEN
                        'represented'
                        ::actor_attribution

                WHEN actual_actor_id
                     IS NOT NULL
                    THEN
                        'exact'
                        ::actor_attribution

                WHEN external_actor_id
                     IS NOT NULL
                    THEN
                        'external'
                        ::actor_attribution

                ELSE
                    'unknown'
                    ::actor_attribution
            END
        """
    )

    op.alter_column(
        "messages",
        "source",
        existing_type=message_source,
        nullable=False,
    )

    op.alter_column(
        "messages",
        "actor_attribution",
        existing_type=actor_attribution,
        nullable=False,
    )


def downgrade() -> None:
    op.drop_column(
        "messages",
        "actor_attribution",
    )

    op.drop_column(
        "messages",
        "source",
    )

    bind = op.get_bind()

    actor_attribution.drop(
        bind,
        checkfirst=True,
    )

    message_source.drop(
        bind,
        checkfirst=True,
    )
