from __future__ import annotations

from sqlalchemy import Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB

from app.db.models import (
    BusinessAuditActorType,
    BusinessAuditLog,
)


def test_business_audit_log_table_name() -> None:
    assert BusinessAuditLog.__tablename__ == "business_audit_logs"


def test_business_audit_actor_type_values() -> None:
    assert {actor_type.value for actor_type in BusinessAuditActorType} == {
        "human",
        "integration",
        "system",
    }


def test_business_audit_log_tenant_id_is_required() -> None:
    column = BusinessAuditLog.__table__.c.tenant_id

    assert column.nullable is False


def test_business_audit_log_tenant_id_is_indexed() -> None:
    column = BusinessAuditLog.__table__.c.tenant_id

    assert column.index is True


def test_business_audit_log_has_direct_tenant_fk() -> None:
    column = BusinessAuditLog.__table__.c.tenant_id

    foreign_keys = [
        foreign_key
        for foreign_key in column.foreign_keys
        if foreign_key.target_fullname == "tenants.id"
    ]

    assert len(foreign_keys) == 1
    assert foreign_keys[0].ondelete == "RESTRICT"


def test_business_audit_log_has_tenant_safe_candidate_key() -> None:
    constraints = [
        constraint
        for constraint in BusinessAuditLog.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
        and constraint.name == "uq_business_audit_logs_tenant_id_id"
    ]

    assert len(constraints) == 1

    constraint = constraints[0]

    assert [column.name for column in constraint.columns] == [
        "tenant_id",
        "id",
    ]


def test_business_audit_actor_fields_are_required() -> None:
    table = BusinessAuditLog.__table__

    assert table.c.actor_type.nullable is False
    assert table.c.actor_id.nullable is False


def test_business_audit_action_is_required() -> None:
    column = BusinessAuditLog.__table__.c.action

    assert column.nullable is False


def test_business_audit_resource_fields_are_required() -> None:
    table = BusinessAuditLog.__table__

    assert table.c.resource_type.nullable is False
    assert table.c.resource_id.nullable is False


def test_business_audit_before_and_after_use_jsonb() -> None:
    table = BusinessAuditLog.__table__

    assert isinstance(
        table.c.before_json.type,
        JSONB,
    )

    assert isinstance(
        table.c.after_json.type,
        JSONB,
    )


def test_business_audit_before_and_after_are_optional() -> None:
    table = BusinessAuditLog.__table__

    assert table.c.before_json.nullable is True
    assert table.c.after_json.nullable is True


def test_business_audit_trace_id_is_required() -> None:
    column = BusinessAuditLog.__table__.c.trace_id

    assert column.nullable is False


def test_business_audit_created_at_is_required() -> None:
    column = BusinessAuditLog.__table__.c.created_at

    assert column.nullable is False
    assert column.server_default is not None


def test_business_audit_has_tenant_timeline_index() -> None:
    indexes = [
        index
        for index in BusinessAuditLog.__table__.indexes
        if isinstance(index, Index) and index.name == "ix_business_audit_logs_tenant_created_at"
    ]

    assert len(indexes) == 1

    index = indexes[0]

    assert [column.name for column in index.columns] == [
        "tenant_id",
        "created_at",
    ]


def test_business_audit_has_resource_timeline_index() -> None:
    indexes = [
        index
        for index in BusinessAuditLog.__table__.indexes
        if isinstance(index, Index)
        and index.name == "ix_business_audit_logs_tenant_resource_created_at"
    ]

    assert len(indexes) == 1

    index = indexes[0]

    assert [column.name for column in index.columns] == [
        "tenant_id",
        "resource_type",
        "resource_id",
        "created_at",
    ]


def test_business_audit_has_actor_timeline_index() -> None:
    indexes = [
        index
        for index in BusinessAuditLog.__table__.indexes
        if isinstance(index, Index)
        and index.name == "ix_business_audit_logs_tenant_actor_created_at"
    ]

    assert len(indexes) == 1

    index = indexes[0]

    assert [column.name for column in index.columns] == [
        "tenant_id",
        "actor_type",
        "actor_id",
        "created_at",
    ]


def test_business_audit_log_is_append_only_shape() -> None:
    column_names = set(
        BusinessAuditLog.__table__.c.keys(),
    )

    assert "updated_at" not in column_names
    assert "active" not in column_names
    assert "deleted_at" not in column_names


def test_business_audit_log_has_no_secret_columns() -> None:
    column_names = set(
        BusinessAuditLog.__table__.c.keys(),
    )

    forbidden_columns = {
        "access_token",
        "token",
        "secret",
        "client_secret",
        "password",
        "api_key",
        "presigned_url",
    }

    assert column_names.isdisjoint(
        forbidden_columns,
    )
