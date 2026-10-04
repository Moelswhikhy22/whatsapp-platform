from __future__ import annotations

from sqlalchemy import ForeignKeyConstraint, Index, UniqueConstraint

from app.db.models import CustomerContact


def test_customer_contact_table_name() -> None:
    assert CustomerContact.__tablename__ == "customer_contacts"


def test_customer_contact_tenant_id_is_required() -> None:
    column = CustomerContact.__table__.c.tenant_id

    assert column.nullable is False


def test_customer_contact_tenant_id_is_indexed() -> None:
    column = CustomerContact.__table__.c.tenant_id

    assert column.index is True


def test_customer_contact_has_direct_tenant_foreign_key() -> None:
    column = CustomerContact.__table__.c.tenant_id

    foreign_keys = [
        foreign_key
        for foreign_key in column.foreign_keys
        if foreign_key.target_fullname == "tenants.id"
    ]

    assert len(foreign_keys) == 1
    assert foreign_keys[0].ondelete == "RESTRICT"


def test_customer_company_id_is_required() -> None:
    column = CustomerContact.__table__.c.customer_company_id

    assert column.nullable is False


def test_customer_contact_has_tenant_safe_company_fk() -> None:
    constraints = [
        constraint
        for constraint in CustomerContact.__table__.constraints
        if isinstance(constraint, ForeignKeyConstraint)
        and constraint.name == "fk_customer_contacts_tenant_company"
    ]

    assert len(constraints) == 1

    constraint = constraints[0]

    assert [element.parent.name for element in constraint.elements] == [
        "tenant_id",
        "customer_company_id",
    ]

    assert [element.target_fullname for element in constraint.elements] == [
        "customer_companies.tenant_id",
        "customer_companies.id",
    ]

    assert constraint.ondelete == "RESTRICT"


def test_customer_contact_has_tenant_safe_candidate_key() -> None:
    constraints = [
        constraint
        for constraint in CustomerContact.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
        and constraint.name == "uq_customer_contacts_tenant_id_id"
    ]

    assert len(constraints) == 1

    constraint = constraints[0]

    assert [column.name for column in constraint.columns] == [
        "tenant_id",
        "id",
    ]


def test_normalized_phone_is_unique_inside_tenant() -> None:
    constraints = [
        constraint
        for constraint in CustomerContact.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
        and constraint.name == "uq_customer_contacts_tenant_id_normalized_phone"
    ]

    assert len(constraints) == 1

    constraint = constraints[0]

    assert [column.name for column in constraint.columns] == [
        "tenant_id",
        "normalized_phone",
    ]


def test_phone_number_is_required() -> None:
    column = CustomerContact.__table__.c.phone_number

    assert column.nullable is False


def test_normalized_phone_is_required() -> None:
    column = CustomerContact.__table__.c.normalized_phone

    assert column.nullable is False


def test_display_name_is_optional() -> None:
    column = CustomerContact.__table__.c.display_name

    assert column.nullable is True


def test_customer_contact_has_company_lookup_index() -> None:
    indexes = [
        index
        for index in CustomerContact.__table__.indexes
        if isinstance(index, Index) and index.name == "ix_customer_contacts_tenant_id_company_id"
    ]

    assert len(indexes) == 1

    index = indexes[0]

    assert [column.name for column in index.columns] == [
        "tenant_id",
        "customer_company_id",
    ]


def test_customer_contact_active_defaults_to_true() -> None:
    column = CustomerContact.__table__.c.active

    assert column.nullable is False
    assert column.server_default is not None


def test_customer_contact_timestamps_are_required() -> None:
    created_at_column = CustomerContact.__table__.c.created_at
    updated_at_column = CustomerContact.__table__.c.updated_at

    assert created_at_column.nullable is False
    assert updated_at_column.nullable is False

    assert created_at_column.server_default is not None
    assert updated_at_column.server_default is not None
