from __future__ import annotations

from sqlalchemy import Index
from sqlalchemy.dialects.postgresql import JSONB

from app.db.models import (
    PlatformAuditActorType,
    PlatformAuditLog,
)


def test_platform_audit_log_table_name() -> None:
    assert PlatformAuditLog.__tablename__ == "platform_audit_logs"


def test_platform_audit_actor_type_values() -> None:
    assert {actor_type.value for actor_type in PlatformAuditActorType} == {
        "human",
        "integration",
        "system",
    }


def test_platform_audit_is_not_tenant_owned() -> None:
    column_names = set(
        PlatformAuditLog.__table__.c.keys(),
    )

    assert "tenant_id" not in column_names


def test_affected_tenant_id_is_optional() -> None:
    column = PlatformAuditLog.__table__.c.affected_tenant_id

    assert column.nullable is True


def test_affected_tenant_has_tenant_fk() -> None:
    column = PlatformAuditLog.__table__.c.affected_tenant_id

    foreign_keys = list(
        column.foreign_keys,
    )

    assert len(foreign_keys) == 1

    foreign_key = foreign_keys[0]

    assert foreign_key.target_fullname == "tenants.id"
    assert foreign_key.ondelete == "RESTRICT"


def test_platform_audit_actor_fields_are_required() -> None:
    table = PlatformAuditLog.__table__

    assert table.c.actor_type.nullable is False
    assert table.c.actor_id.nullable is False


def test_platform_audit_action_is_required() -> None:
    column = PlatformAuditLog.__table__.c.action

    assert column.nullable is False


def test_platform_audit_resource_fields_are_optional() -> None:
    table = PlatformAuditLog.__table__

    assert table.c.resource_type.nullable is True
    assert table.c.resource_id.nullable is True


def test_platform_audit_before_and_after_use_jsonb() -> None:
    table = PlatformAuditLog.__table__

    assert isinstance(
        table.c.before_json.type,
        JSONB,
    )

    assert isinstance(
        table.c.after_json.type,
        JSONB,
    )


def test_platform_audit_before_and_after_are_optional() -> None:
    table = PlatformAuditLog.__table__

    assert table.c.before_json.nullable is True
    assert table.c.after_json.nullable is True


def test_platform_audit_trace_id_is_required() -> None:
    column = PlatformAuditLog.__table__.c.trace_id

    assert column.nullable is False


def test_platform_audit_created_at_is_required() -> None:
    column = PlatformAuditLog.__table__.c.created_at

    assert column.nullable is False
    assert column.server_default is not None


def test_platform_audit_has_global_timeline_index() -> None:
    indexes = [
        index
        for index in PlatformAuditLog.__table__.indexes
        if isinstance(index, Index) and index.name == "ix_platform_audit_logs_created_at"
    ]

    assert len(indexes) == 1

    index = indexes[0]

    assert [column.name for column in index.columns] == [
        "created_at",
    ]


def test_platform_audit_has_affected_tenant_timeline_index() -> None:
    indexes = [
        index
        for index in PlatformAuditLog.__table__.indexes
        if isinstance(index, Index)
        and index.name == "ix_platform_audit_logs_affected_tenant_created_at"
    ]

    assert len(indexes) == 1

    index = indexes[0]

    assert [column.name for column in index.columns] == [
        "affected_tenant_id",
        "created_at",
    ]


def test_platform_audit_has_actor_timeline_index() -> None:
    indexes = [
        index
        for index in PlatformAuditLog.__table__.indexes
        if isinstance(index, Index) and index.name == "ix_platform_audit_logs_actor_created_at"
    ]

    assert len(indexes) == 1

    index = indexes[0]

    assert [column.name for column in index.columns] == [
        "actor_type",
        "actor_id",
        "created_at",
    ]


def test_platform_audit_has_resource_timeline_index() -> None:
    indexes = [
        index
        for index in PlatformAuditLog.__table__.indexes
        if isinstance(index, Index) and index.name == "ix_platform_audit_logs_resource_created_at"
    ]

    assert len(indexes) == 1

    index = indexes[0]

    assert [column.name for column in index.columns] == [
        "resource_type",
        "resource_id",
        "created_at",
    ]


def test_platform_audit_log_is_append_only_shape() -> None:
    column_names = set(
        PlatformAuditLog.__table__.c.keys(),
    )

    assert "updated_at" not in column_names
    assert "active" not in column_names
    assert "deleted_at" not in column_names


def test_platform_audit_log_has_no_secret_columns() -> None:
    column_names = set(
        PlatformAuditLog.__table__.c.keys(),
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
