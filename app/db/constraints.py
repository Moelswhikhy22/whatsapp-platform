from __future__ import annotations

from sqlalchemy import ForeignKeyConstraint


def tenant_composite_foreign_key(
    *,
    local_resource_column: str,
    target_table: str,
    constraint_name: str,
    target_resource_column: str = "id",
    ondelete: str | None = "RESTRICT",
) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(
        [
            "tenant_id",
            local_resource_column,
        ],
        [
            f"{target_table}.tenant_id",
            f"{target_table}.{target_resource_column}",
        ],
        name=constraint_name,
        ondelete=ondelete,
    )
