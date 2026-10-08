from __future__ import annotations

from sqlalchemy import ForeignKeyConstraint, Index, UniqueConstraint

from app.db.models import ExternalIdentity


def test_external_identity_table_name() -> None:
    assert ExternalIdentity.__tablename__ == "external_identities"


def test_external_identity_tenant_id_is_required() -> None:
    column = ExternalIdentity.__table__.c.tenant_id

    assert column.nullable is False


def test_external_identity_tenant_id_is_indexed() -> None:
    column = ExternalIdentity.__table__.c.tenant_id

    assert column.index is True


def test_external_identity_has_direct_tenant_fk() -> None:
    column = ExternalIdentity.__table__.c.tenant_id

    foreign_keys = [
        foreign_key
        for foreign_key in column.foreign_keys
        if foreign_key.target_fullname == "tenants.id"
    ]

    assert len(foreign_keys) == 1
    assert foreign_keys[0].ondelete == "RESTRICT"


def test_external_identity_has_tenant_safe_candidate_key() -> None:
    constraints = [
        constraint
        for constraint in ExternalIdentity.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
        and constraint.name == "uq_external_identities_tenant_id_id"
    ]

    assert len(constraints) == 1

    constraint = constraints[0]

    assert [column.name for column in constraint.columns] == [
        "tenant_id",
        "id",
    ]


def test_external_identity_provider_is_required() -> None:
    column = ExternalIdentity.__table__.c.provider

    assert column.nullable is False


def test_external_user_id_is_required() -> None:
    column = ExternalIdentity.__table__.c.external_user_id

    assert column.nullable is False


def test_external_identity_is_unique_inside_tenant_provider() -> None:
    constraints = [
        constraint
        for constraint in ExternalIdentity.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
        and constraint.name == ("uq_external_identities_tenant_provider_external_user_id")
    ]

    assert len(constraints) == 1

    constraint = constraints[0]

    assert [column.name for column in constraint.columns] == [
        "tenant_id",
        "provider",
        "external_user_id",
    ]


def test_external_identity_employee_id_is_required() -> None:
    column = ExternalIdentity.__table__.c.employee_id

    assert column.nullable is False


def test_external_identity_has_tenant_safe_employee_fk() -> None:
    constraints = [
        constraint
        for constraint in ExternalIdentity.__table__.constraints
        if isinstance(constraint, ForeignKeyConstraint)
        and constraint.name == "fk_external_identities_tenant_employee"
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


def test_external_identity_has_employee_lookup_index() -> None:
    indexes = [
        index
        for index in ExternalIdentity.__table__.indexes
        if isinstance(index, Index) and index.name == "ix_external_identities_tenant_employee_id"
    ]

    assert len(indexes) == 1

    index = indexes[0]

    assert [column.name for column in index.columns] == [
        "tenant_id",
        "employee_id",
    ]


def test_external_identity_timestamps_are_required() -> None:
    created_at_column = ExternalIdentity.__table__.c.created_at
    updated_at_column = ExternalIdentity.__table__.c.updated_at

    assert created_at_column.nullable is False
    assert updated_at_column.nullable is False

    assert created_at_column.server_default is not None
    assert updated_at_column.server_default is not None


def test_external_identity_does_not_store_permissions() -> None:
    column_names = set(
        ExternalIdentity.__table__.c.keys(),
    )

    forbidden_columns = {
        "role",
        "role_id",
        "permissions",
        "group_id",
    }

    assert column_names.isdisjoint(
        forbidden_columns,
    )


def test_external_identity_does_not_store_authentication_secrets() -> None:
    column_names = set(
        ExternalIdentity.__table__.c.keys(),
    )

    forbidden_columns = {
        "password",
        "access_token",
        "refresh_token",
        "client_secret",
        "api_key",
    }

    assert column_names.isdisjoint(
        forbidden_columns,
    )
