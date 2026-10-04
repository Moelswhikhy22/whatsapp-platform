from __future__ import annotations

from sqlalchemy import ForeignKeyConstraint, Index, UniqueConstraint

from app.db.models import (
    GroupMembership,
)


def test_group_membership_table_name() -> None:
    assert GroupMembership.__tablename__ == "group_memberships"


def test_group_membership_tenant_id_is_required() -> None:
    tenant_column = GroupMembership.__table__.c.tenant_id

    assert tenant_column.nullable is False


def test_group_membership_group_id_is_required() -> None:
    group_column = GroupMembership.__table__.c.group_id

    assert group_column.nullable is False


def test_group_membership_employee_id_is_required() -> None:
    employee_column = GroupMembership.__table__.c.employee_id

    assert employee_column.nullable is False


def test_group_membership_has_direct_tenant_foreign_key() -> None:
    tenant_column = GroupMembership.__table__.c.tenant_id

    tenant_foreign_keys = [
        foreign_key
        for foreign_key in tenant_column.foreign_keys
        if foreign_key.target_fullname == "tenants.id"
    ]

    assert len(tenant_foreign_keys) == 1
    assert tenant_foreign_keys[0].ondelete == "RESTRICT"


def test_group_membership_has_tenant_safe_group_foreign_key() -> None:
    constraints = [
        constraint
        for constraint in GroupMembership.__table__.constraints
        if isinstance(constraint, ForeignKeyConstraint)
        and constraint.name == "fk_group_memberships_tenant_group"
    ]

    assert len(constraints) == 1

    constraint = constraints[0]

    assert [element.parent.name for element in constraint.elements] == [
        "tenant_id",
        "group_id",
    ]

    assert [element.target_fullname for element in constraint.elements] == [
        "groups.tenant_id",
        "groups.id",
    ]

    assert constraint.ondelete == "RESTRICT"


def test_group_membership_has_tenant_safe_employee_foreign_key() -> None:
    constraints = [
        constraint
        for constraint in GroupMembership.__table__.constraints
        if isinstance(constraint, ForeignKeyConstraint)
        and constraint.name == "fk_group_memberships_tenant_employee"
    ]

    assert len(constraints) == 1

    constraint = constraints[0]

    assert [element.parent.name for element in constraint.elements] == [
        "tenant_id",
        "employee_id",
    ]

    assert [element.target_fullname for element in constraint.elements] == [
        "employees.tenant_id",
        "employees.id",
    ]

    assert constraint.ondelete == "RESTRICT"


def test_group_membership_has_tenant_safe_candidate_key() -> None:
    constraints = [
        constraint
        for constraint in GroupMembership.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
        and constraint.name == "uq_group_memberships_tenant_id_id"
    ]

    assert len(constraints) == 1

    constraint = constraints[0]

    assert [column.name for column in constraint.columns] == [
        "tenant_id",
        "id",
    ]


def test_employee_can_have_only_one_membership_per_group() -> None:
    constraints = [
        constraint
        for constraint in GroupMembership.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
        and constraint.name == "uq_group_memberships_tenant_id_group_id_employee_id"
    ]

    assert len(constraints) == 1

    constraint = constraints[0]

    assert [column.name for column in constraint.columns] == [
        "tenant_id",
        "group_id",
        "employee_id",
    ]


def test_group_membership_has_employee_lookup_index() -> None:
    indexes = [
        index
        for index in GroupMembership.__table__.indexes
        if isinstance(index, Index) and index.name == "ix_group_memberships_tenant_id_employee_id"
    ]

    assert len(indexes) == 1

    index = indexes[0]

    assert [column.name for column in index.columns] == [
        "tenant_id",
        "employee_id",
    ]


def test_group_membership_is_admin_defaults_to_false() -> None:
    column = GroupMembership.__table__.c.is_admin

    assert column.nullable is False
    assert column.server_default is not None


def test_group_membership_active_defaults_to_true() -> None:
    column = GroupMembership.__table__.c.active

    assert column.nullable is False
    assert column.server_default is not None


def test_group_membership_timestamps_are_required() -> None:
    created_at_column = GroupMembership.__table__.c.created_at
    updated_at_column = GroupMembership.__table__.c.updated_at

    assert created_at_column.nullable is False
    assert updated_at_column.nullable is False

    assert created_at_column.server_default is not None
    assert updated_at_column.server_default is not None
