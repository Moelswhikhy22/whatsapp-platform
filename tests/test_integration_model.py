from __future__ import annotations

from sqlalchemy import UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB

from app.db.models import (
    Integration,
    IntegrationProvider,
)


def test_integration_table_name() -> None:
    assert Integration.__tablename__ == "integrations"


def test_integration_provider_values() -> None:
    assert {provider.value for provider in IntegrationProvider} == {
        "meta",
        "odoo",
    }


def test_integration_tenant_id_is_required() -> None:
    tenant_column = Integration.__table__.c.tenant_id

    assert tenant_column.nullable is False


def test_integration_tenant_id_is_indexed() -> None:
    tenant_column = Integration.__table__.c.tenant_id

    assert tenant_column.index is True


def test_integration_tenant_foreign_key_targets_tenants() -> None:
    tenant_column = Integration.__table__.c.tenant_id

    foreign_keys = list(tenant_column.foreign_keys)

    assert len(foreign_keys) == 1

    foreign_key = foreign_keys[0]

    assert foreign_key.target_fullname == "tenants.id"
    assert foreign_key.ondelete == "RESTRICT"


def test_integration_has_tenant_safe_candidate_key() -> None:
    constraints = [
        constraint
        for constraint in Integration.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
        and constraint.name == "uq_integrations_tenant_id_id"
    ]

    assert len(constraints) == 1

    constraint = constraints[0]

    assert [column.name for column in constraint.columns] == [
        "tenant_id",
        "id",
    ]


def test_integration_name_is_unique_per_provider_inside_tenant() -> None:
    constraints = [
        constraint
        for constraint in Integration.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
        and constraint.name == "uq_integrations_tenant_id_provider_name"
    ]

    assert len(constraints) == 1

    constraint = constraints[0]

    assert [column.name for column in constraint.columns] == [
        "tenant_id",
        "provider",
        "name",
    ]


def test_external_account_id_is_unique_per_provider_inside_tenant() -> None:
    constraints = [
        constraint
        for constraint in Integration.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
        and constraint.name == ("uq_integrations_tenant_id_provider_external_account_id")
    ]

    assert len(constraints) == 1

    constraint = constraints[0]

    assert [column.name for column in constraint.columns] == [
        "tenant_id",
        "provider",
        "external_account_id",
    ]


def test_integration_provider_is_required() -> None:
    provider_column = Integration.__table__.c.provider

    assert provider_column.nullable is False


def test_integration_name_is_required() -> None:
    name_column = Integration.__table__.c.name

    assert name_column.nullable is False


def test_external_account_id_is_optional() -> None:
    external_account_column = Integration.__table__.c.external_account_id

    assert external_account_column.nullable is True


def test_integration_config_uses_jsonb() -> None:
    config_column = Integration.__table__.c.config_json

    assert isinstance(
        config_column.type,
        JSONB,
    )

    assert config_column.nullable is False
    assert config_column.server_default is not None


def test_vault_secret_reference_is_optional() -> None:
    vault_reference_column = Integration.__table__.c.vault_secret_reference

    assert vault_reference_column.nullable is True


def test_integration_has_no_plaintext_secret_columns() -> None:
    column_names = set(
        Integration.__table__.c.keys(),
    )

    forbidden_columns = {
        "access_token",
        "token",
        "secret",
        "client_secret",
        "password",
        "api_key",
        "app_secret",
    }

    assert column_names.isdisjoint(
        forbidden_columns,
    )


def test_integration_active_defaults_to_true() -> None:
    active_column = Integration.__table__.c.active

    assert active_column.nullable is False
    assert active_column.server_default is not None


def test_integration_timestamps_are_required() -> None:
    created_at_column = Integration.__table__.c.created_at
    updated_at_column = Integration.__table__.c.updated_at

    assert created_at_column.nullable is False
    assert updated_at_column.nullable is False

    assert created_at_column.server_default is not None
    assert updated_at_column.server_default is not None
