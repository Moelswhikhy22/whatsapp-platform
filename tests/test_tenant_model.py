from app.db.base import Base
from app.db.models.tenant import Tenant, TenantStatus


def test_tenant_model_is_registered() -> None:
    assert Tenant.__tablename__ == "tenants"
    assert "tenants" in Base.metadata.tables


def test_tenant_table_has_expected_columns() -> None:
    table = Tenant.__table__

    assert set(table.columns.keys()) == {
        "id",
        "name",
        "slug",
        "created_at",
        "status",
        "updated_at",
    }


def test_tenant_id_is_primary_key() -> None:
    table = Tenant.__table__

    assert table.c.id.primary_key is True
    assert table.c.id.nullable is False


def test_tenant_name_is_required() -> None:
    table = Tenant.__table__

    assert table.c.name.nullable is False


def test_tenant_slug_is_required_and_unique() -> None:
    table = Tenant.__table__

    assert table.c.slug.nullable is False

    unique_constraint_names = {
        constraint.name for constraint in table.constraints if constraint.name is not None
    }

    assert "uq_tenants_slug" in unique_constraint_names


def test_tenant_timestamps_are_required() -> None:
    table = Tenant.__table__

    assert table.c.created_at.nullable is False
    assert table.c.updated_at.nullable is False


def test_tenant_status_is_required() -> None:
    table = Tenant.__table__

    assert table.c.status.nullable is False


def test_tenant_status_defaults_to_active() -> None:
    table = Tenant.__table__
    column = table.c.status

    assert column.default is not None
    assert column.default.arg == TenantStatus.ACTIVE

    assert column.server_default is not None


def test_tenant_status_values_are_expected() -> None:
    assert {status.value for status in TenantStatus} == {
        "active",
        "suspended",
        "disabled",
    }
