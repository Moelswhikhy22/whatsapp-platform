from sqlalchemy import ForeignKeyConstraint, UniqueConstraint

from app.db.base import Base
from app.db.models.tenant_membership import TenantMembership


def test_membership_has_tenant_scoped_role_uniqueness() -> None:
    table = TenantMembership.__table__

    constraints = {
        constraint.name: tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if isinstance(
            constraint,
            UniqueConstraint,
        )
    }

    assert constraints["uq_tenant_memberships_tenant_id_user_id_role_id"] == (
        "tenant_id",
        "user_id",
        "role_id",
    )


def test_membership_has_composite_tenant_identity() -> None:
    table = TenantMembership.__table__

    constraints = {
        constraint.name: tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if isinstance(
            constraint,
            UniqueConstraint,
        )
    }

    assert constraints["uq_tenant_memberships_tenant_id_id"] == (
        "tenant_id",
        "id",
    )


def test_tenant_membership_model_is_registered() -> None:
    assert TenantMembership.__tablename__ == "tenant_memberships"
    assert "tenant_memberships" in Base.metadata.tables


def test_tenant_membership_has_expected_columns() -> None:
    table = TenantMembership.__table__

    assert set(table.columns.keys()) == {
        "id",
        "tenant_id",
        "user_id",
        "role_id",
        "active",
        "created_at",
    }


def test_tenant_membership_id_is_primary_key() -> None:
    table = TenantMembership.__table__

    assert table.c.id.primary_key is True
    assert table.c.id.nullable is False


def test_tenant_membership_requires_tenant() -> None:
    table = TenantMembership.__table__

    assert table.c.tenant_id.nullable is False


def test_tenant_membership_has_tenant_foreign_key() -> None:
    table = TenantMembership.__table__

    foreign_keys = {
        foreign_key.target_fullname
        for constraint in table.constraints
        if isinstance(constraint, ForeignKeyConstraint)
        for foreign_key in constraint.elements
    }

    assert "tenants.id" in foreign_keys


def test_tenant_membership_requires_user() -> None:
    table = TenantMembership.__table__

    assert table.c.user_id.nullable is False


def test_tenant_membership_requires_role() -> None:
    table = TenantMembership.__table__

    assert table.c.role_id.nullable is False


def test_tenant_membership_active_is_required() -> None:
    table = TenantMembership.__table__

    assert table.c.active.nullable is False


def test_tenant_membership_created_at_is_required() -> None:
    table = TenantMembership.__table__

    assert table.c.created_at.nullable is False
