from __future__ import annotations

from sqlalchemy import CheckConstraint, Index

from app.db.models import (
    SecurityAccessLog,
    SecurityAccessOutcome,
    SecurityPrincipalType,
)


def test_security_access_log_table_name() -> None:
    assert SecurityAccessLog.__tablename__ == "security_access_logs"


def test_security_principal_type_values() -> None:
    assert {principal_type.value for principal_type in SecurityPrincipalType} == {
        "anonymous",
        "human",
        "integration",
        "system",
    }


def test_security_access_outcome_values() -> None:
    assert {outcome.value for outcome in SecurityAccessOutcome} == {
        "success",
        "denied",
        "failure",
    }


def test_security_access_tenant_id_is_optional() -> None:
    column = SecurityAccessLog.__table__.c.tenant_id

    assert column.nullable is True


def test_security_access_has_optional_tenant_fk() -> None:
    column = SecurityAccessLog.__table__.c.tenant_id

    foreign_keys = list(
        column.foreign_keys,
    )

    assert len(foreign_keys) == 1

    foreign_key = foreign_keys[0]

    assert foreign_key.target_fullname == "tenants.id"
    assert foreign_key.ondelete == "RESTRICT"


def test_security_access_principal_type_is_required() -> None:
    column = SecurityAccessLog.__table__.c.principal_type

    assert column.nullable is False


def test_security_access_principal_id_is_optional_at_column_level() -> None:
    column = SecurityAccessLog.__table__.c.principal_id

    assert column.nullable is True


def test_security_access_has_principal_identity_check() -> None:
    constraints = [
        constraint
        for constraint in SecurityAccessLog.__table__.constraints
        if isinstance(constraint, CheckConstraint)
        and constraint.name == "ck_security_access_logs_principal_identity"
    ]

    assert len(constraints) == 1


def test_security_access_event_is_required() -> None:
    column = SecurityAccessLog.__table__.c.event

    assert column.nullable is False


def test_security_access_outcome_is_required() -> None:
    column = SecurityAccessLog.__table__.c.outcome

    assert column.nullable is False


def test_security_access_resource_fields_are_optional() -> None:
    table = SecurityAccessLog.__table__

    assert table.c.resource_type.nullable is True
    assert table.c.resource_id.nullable is True


def test_security_access_request_fields_are_optional() -> None:
    table = SecurityAccessLog.__table__

    assert table.c.request_method.nullable is True
    assert table.c.request_path.nullable is True


def test_security_access_network_fields_are_optional() -> None:
    table = SecurityAccessLog.__table__

    assert table.c.client_ip.nullable is True
    assert table.c.user_agent.nullable is True


def test_security_access_reason_code_is_optional() -> None:
    column = SecurityAccessLog.__table__.c.reason_code

    assert column.nullable is True


def test_security_access_trace_id_is_required() -> None:
    column = SecurityAccessLog.__table__.c.trace_id

    assert column.nullable is False


def test_security_access_created_at_is_required() -> None:
    column = SecurityAccessLog.__table__.c.created_at

    assert column.nullable is False
    assert column.server_default is not None


def test_security_access_has_global_timeline_index() -> None:
    indexes = [
        index
        for index in SecurityAccessLog.__table__.indexes
        if isinstance(index, Index) and index.name == "ix_security_access_logs_created_at"
    ]

    assert len(indexes) == 1

    index = indexes[0]

    assert [column.name for column in index.columns] == [
        "created_at",
    ]


def test_security_access_has_tenant_timeline_index() -> None:
    indexes = [
        index
        for index in SecurityAccessLog.__table__.indexes
        if isinstance(index, Index) and index.name == "ix_security_access_logs_tenant_created_at"
    ]

    assert len(indexes) == 1

    index = indexes[0]

    assert [column.name for column in index.columns] == [
        "tenant_id",
        "created_at",
    ]


def test_security_access_has_event_outcome_index() -> None:
    indexes = [
        index
        for index in SecurityAccessLog.__table__.indexes
        if isinstance(index, Index)
        and index.name == "ix_security_access_logs_event_outcome_created_at"
    ]

    assert len(indexes) == 1

    index = indexes[0]

    assert [column.name for column in index.columns] == [
        "event",
        "outcome",
        "created_at",
    ]


def test_security_access_has_principal_timeline_index() -> None:
    indexes = [
        index
        for index in SecurityAccessLog.__table__.indexes
        if isinstance(index, Index) and index.name == "ix_security_access_logs_principal_created_at"
    ]

    assert len(indexes) == 1

    index = indexes[0]

    assert [column.name for column in index.columns] == [
        "principal_type",
        "principal_id",
        "created_at",
    ]


def test_security_access_has_trace_id_index() -> None:
    indexes = [
        index
        for index in SecurityAccessLog.__table__.indexes
        if isinstance(index, Index) and index.name == "ix_security_access_logs_trace_id"
    ]

    assert len(indexes) == 1

    index = indexes[0]

    assert [column.name for column in index.columns] == [
        "trace_id",
    ]


def test_security_access_log_is_append_only_shape() -> None:
    column_names = set(
        SecurityAccessLog.__table__.c.keys(),
    )

    assert "updated_at" not in column_names
    assert "active" not in column_names
    assert "deleted_at" not in column_names


def test_security_access_log_has_no_sensitive_request_columns() -> None:
    column_names = set(
        SecurityAccessLog.__table__.c.keys(),
    )

    forbidden_columns = {
        "authorization",
        "authorization_header",
        "cookie",
        "cookies",
        "access_token",
        "refresh_token",
        "password",
        "request_body",
        "presigned_url",
    }

    assert column_names.isdisjoint(
        forbidden_columns,
    )
