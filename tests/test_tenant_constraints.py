from sqlalchemy import (
    Column,
    MetaData,
    Table,
    Uuid,
)

from app.db.constraints import (
    tenant_composite_foreign_key,
)


def test_tenant_composite_foreign_key_shape() -> None:
    metadata = MetaData()

    Table(
        "parents",
        metadata,
        Column(
            "tenant_id",
            Uuid(),
            nullable=False,
        ),
        Column(
            "id",
            Uuid(),
            nullable=False,
        ),
    )

    child = Table(
        "children",
        metadata,
        Column(
            "tenant_id",
            Uuid(),
            nullable=False,
        ),
        Column(
            "parent_id",
            Uuid(),
            nullable=False,
        ),
        tenant_composite_foreign_key(
            local_resource_column="parent_id",
            target_table="parents",
            constraint_name=("fk_children_tenant_id_parent_id_parents"),
        ),
    )

    constraint = next(
        constraint
        for constraint in child.constraints
        if constraint.name == "fk_children_tenant_id_parent_id_parents"
    )

    assert tuple(column.name for column in constraint.columns) == (
        "tenant_id",
        "parent_id",
    )

    assert [element.target_fullname for element in constraint.elements] == [
        "parents.tenant_id",
        "parents.id",
    ]


def test_tenant_composite_foreign_key_uses_restrict_by_default() -> None:
    constraint = tenant_composite_foreign_key(
        local_resource_column="parent_id",
        target_table="parents",
        constraint_name="fk_test",
    )

    assert all(element.ondelete == "RESTRICT" for element in constraint.elements)
