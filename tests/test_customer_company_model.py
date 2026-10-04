from __future__ import annotations

from sqlalchemy import UniqueConstraint

from app.db.models import CustomerCompany


def test_customer_company_table_name() -> None:
    assert CustomerCompany.__tablename__ == "customer_companies"


def test_customer_company_tenant_id_is_required() -> None:
    tenant_column = CustomerCompany.__table__.c.tenant_id

    assert tenant_column.nullable is False


def test_customer_company_tenant_id_is_indexed() -> None:
    tenant_column = CustomerCompany.__table__.c.tenant_id

    assert tenant_column.index is True


def test_customer_company_tenant_foreign_key_targets_tenants() -> None:
    tenant_column = CustomerCompany.__table__.c.tenant_id

    foreign_keys = list(tenant_column.foreign_keys)

    assert len(foreign_keys) == 1

    foreign_key = foreign_keys[0]

    assert foreign_key.target_fullname == "tenants.id"
    assert foreign_key.ondelete == "RESTRICT"


def test_customer_company_has_tenant_safe_candidate_key() -> None:
    constraints = [
        constraint
        for constraint in CustomerCompany.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
        and constraint.name == "uq_customer_companies_tenant_id_id"
    ]

    assert len(constraints) == 1

    constraint = constraints[0]

    assert [column.name for column in constraint.columns] == [
        "tenant_id",
        "id",
    ]


def test_customer_company_name_is_required() -> None:
    name_column = CustomerCompany.__table__.c.name

    assert name_column.nullable is False


def test_customer_company_active_defaults_to_true() -> None:
    active_column = CustomerCompany.__table__.c.active

    assert active_column.nullable is False
    assert active_column.server_default is not None


def test_customer_company_timestamps_are_required() -> None:
    created_at_column = CustomerCompany.__table__.c.created_at
    updated_at_column = CustomerCompany.__table__.c.updated_at

    assert created_at_column.nullable is False
    assert updated_at_column.nullable is False

    assert created_at_column.server_default is not None
    assert updated_at_column.server_default is not None
