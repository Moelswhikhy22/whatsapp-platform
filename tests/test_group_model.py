from __future__ import annotations

from sqlalchemy import UniqueConstraint

from app.db.models.group import Group


def test_group_table_name() -> None:
    assert Group.__tablename__ == "groups"


def test_group_tenant_id_is_required() -> None:
    tenant_column = Group.__table__.c.tenant_id

    assert tenant_column.nullable is False


def test_group_tenant_id_is_indexed() -> None:
    tenant_column = Group.__table__.c.tenant_id

    assert tenant_column.index is True


def test_group_tenant_foreign_key_targets_tenants() -> None:
    tenant_column = Group.__table__.c.tenant_id

    foreign_keys = list(tenant_column.foreign_keys)

    assert len(foreign_keys) == 1

    foreign_key = foreign_keys[0]

    assert foreign_key.target_fullname == "tenants.id"
    assert foreign_key.ondelete == "RESTRICT"


def test_group_has_tenant_safe_candidate_key() -> None:
    unique_constraints = [
        constraint
        for constraint in Group.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    ]

    matching_constraints = [
        constraint
        for constraint in unique_constraints
        if constraint.name == "uq_groups_tenant_id_id"
    ]

    assert len(matching_constraints) == 1

    constraint = matching_constraints[0]

    assert [column.name for column in constraint.columns] == [
        "tenant_id",
        "id",
    ]


def test_group_name_is_unique_inside_tenant() -> None:
    unique_constraints = [
        constraint
        for constraint in Group.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    ]

    matching_constraints = [
        constraint
        for constraint in unique_constraints
        if constraint.name == "uq_groups_tenant_id_name"
    ]

    assert len(matching_constraints) == 1

    constraint = matching_constraints[0]

    assert [column.name for column in constraint.columns] == [
        "tenant_id",
        "name",
    ]


def test_group_name_is_required() -> None:
    name_column = Group.__table__.c.name

    assert name_column.nullable is False


def test_group_active_is_required() -> None:
    active_column = Group.__table__.c.active

    assert active_column.nullable is False
    assert active_column.server_default is not None


def test_group_timestamps_are_required() -> None:
    created_at_column = Group.__table__.c.created_at
    updated_at_column = Group.__table__.c.updated_at

    assert created_at_column.nullable is False
    assert updated_at_column.nullable is False

    assert created_at_column.server_default is not None
    assert updated_at_column.server_default is not None
