from __future__ import annotations

from sqlalchemy import UniqueConstraint

from app.db.models.employee import Employee


def test_employee_table_name() -> None:
    assert Employee.__tablename__ == "employees"


def test_employee_tenant_id_is_required() -> None:
    tenant_column = Employee.__table__.c.tenant_id

    assert tenant_column.nullable is False


def test_employee_tenant_id_is_indexed() -> None:
    tenant_column = Employee.__table__.c.tenant_id

    assert tenant_column.index is True


def test_employee_tenant_foreign_key_targets_tenants() -> None:
    tenant_column = Employee.__table__.c.tenant_id

    foreign_keys = list(tenant_column.foreign_keys)

    assert len(foreign_keys) == 1

    foreign_key = foreign_keys[0]

    assert foreign_key.target_fullname == "tenants.id"
    assert foreign_key.ondelete == "RESTRICT"


def test_employee_has_tenant_safe_candidate_key() -> None:
    unique_constraints = [
        constraint
        for constraint in Employee.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    ]

    matching_constraints = [
        constraint
        for constraint in unique_constraints
        if constraint.name == "uq_employees_tenant_id_id"
    ]

    assert len(matching_constraints) == 1

    constraint = matching_constraints[0]

    assert [column.name for column in constraint.columns] == [
        "tenant_id",
        "id",
    ]


def test_employee_display_name_is_required() -> None:
    display_name_column = Employee.__table__.c.display_name

    assert display_name_column.nullable is False


def test_employee_active_is_required() -> None:
    active_column = Employee.__table__.c.active

    assert active_column.nullable is False
    assert active_column.server_default is not None


def test_employee_timestamps_are_required() -> None:
    created_at_column = Employee.__table__.c.created_at
    updated_at_column = Employee.__table__.c.updated_at

    assert created_at_column.nullable is False
    assert updated_at_column.nullable is False

    assert created_at_column.server_default is not None
    assert updated_at_column.server_default is not None
