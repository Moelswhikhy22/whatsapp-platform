from sqlalchemy import ForeignKeyConstraint, UniqueConstraint

from app.db.base import Base
from app.db.models.tenant_domain import TenantDomain


def test_tenant_domain_model_is_registered() -> None:
    assert TenantDomain.__tablename__ == "tenant_domains"
    assert "tenant_domains" in Base.metadata.tables


def test_tenant_domain_has_expected_columns() -> None:
    table = TenantDomain.__table__

    assert set(table.columns.keys()) == {
        "id",
        "tenant_id",
        "hostname",
        "active",
    }


def test_tenant_domain_id_is_primary_key() -> None:
    table = TenantDomain.__table__

    assert table.c.id.primary_key is True
    assert table.c.id.nullable is False


def test_tenant_domain_requires_tenant_id() -> None:
    table = TenantDomain.__table__

    assert table.c.tenant_id.nullable is False


def test_tenant_domain_has_tenant_foreign_key() -> None:
    table = TenantDomain.__table__

    foreign_keys = {
        foreign_key.target_fullname
        for constraint in table.constraints
        if isinstance(constraint, ForeignKeyConstraint)
        for foreign_key in constraint.elements
    }

    assert "tenants.id" in foreign_keys


def test_tenant_domain_hostname_is_required() -> None:
    table = TenantDomain.__table__

    assert table.c.hostname.nullable is False


def test_tenant_domain_hostname_is_globally_unique() -> None:
    table = TenantDomain.__table__

    unique_constraints = {
        constraint.name
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }

    assert "uq_tenant_domains_hostname" in unique_constraints


def test_tenant_domain_active_is_required() -> None:
    table = TenantDomain.__table__

    assert table.c.active.nullable is False


def test_tenant_domain_has_composite_tenant_identity() -> None:
    table = TenantDomain.__table__

    constraints = {
        constraint.name: tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if isinstance(
            constraint,
            UniqueConstraint,
        )
    }

    assert constraints["uq_tenant_domains_tenant_id_id"] == (
        "tenant_id",
        "id",
    )
