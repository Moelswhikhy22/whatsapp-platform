from __future__ import annotations

from sqlalchemy import CheckConstraint, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB

from app.db.models import (
    OutboxEvent,
    OutboxEventStatus,
)


def test_outbox_event_table_name() -> None:
    assert OutboxEvent.__tablename__ == "outbox_events"


def test_outbox_event_status_values() -> None:
    assert {status.value for status in OutboxEventStatus} == {
        "pending",
        "published",
        "failed",
    }


def test_outbox_event_tenant_id_is_required() -> None:
    column = OutboxEvent.__table__.c.tenant_id

    assert column.nullable is False


def test_outbox_event_tenant_id_is_indexed() -> None:
    column = OutboxEvent.__table__.c.tenant_id

    assert column.index is True


def test_outbox_event_has_direct_tenant_fk() -> None:
    column = OutboxEvent.__table__.c.tenant_id

    foreign_keys = [
        foreign_key
        for foreign_key in column.foreign_keys
        if foreign_key.target_fullname == "tenants.id"
    ]

    assert len(foreign_keys) == 1
    assert foreign_keys[0].ondelete == "RESTRICT"


def test_outbox_event_has_tenant_safe_candidate_key() -> None:
    constraints = [
        constraint
        for constraint in OutboxEvent.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
        and constraint.name == "uq_outbox_events_tenant_id_id"
    ]

    assert len(constraints) == 1

    constraint = constraints[0]

    assert [column.name for column in constraint.columns] == [
        "tenant_id",
        "id",
    ]


def test_outbox_event_type_is_required() -> None:
    column = OutboxEvent.__table__.c.event_type

    assert column.nullable is False


def test_outbox_aggregate_fields_are_required() -> None:
    table = OutboxEvent.__table__

    assert table.c.aggregate_type.nullable is False
    assert table.c.aggregate_id.nullable is False


def test_outbox_payload_is_required_jsonb() -> None:
    column = OutboxEvent.__table__.c.payload_json

    assert column.nullable is False
    assert isinstance(
        column.type,
        JSONB,
    )


def test_outbox_status_is_required_with_default() -> None:
    column = OutboxEvent.__table__.c.status

    assert column.nullable is False
    assert column.server_default is not None


def test_outbox_attempts_is_required_with_default() -> None:
    column = OutboxEvent.__table__.c.attempts

    assert column.nullable is False
    assert column.server_default is not None


def test_outbox_attempts_cannot_be_negative() -> None:
    constraints = [
        constraint
        for constraint in OutboxEvent.__table__.constraints
        if isinstance(constraint, CheckConstraint)
        and constraint.name == "ck_outbox_events_attempts_non_negative"
    ]

    assert len(constraints) == 1


def test_outbox_has_published_state_check() -> None:
    constraints = [
        constraint
        for constraint in OutboxEvent.__table__.constraints
        if isinstance(constraint, CheckConstraint)
        and constraint.name == "ck_outbox_events_published_state"
    ]

    assert len(constraints) == 1


def test_outbox_available_at_is_required() -> None:
    column = OutboxEvent.__table__.c.available_at

    assert column.nullable is False
    assert column.server_default is not None


def test_outbox_last_error_is_optional() -> None:
    column = OutboxEvent.__table__.c.last_error

    assert column.nullable is True


def test_outbox_published_at_is_optional() -> None:
    column = OutboxEvent.__table__.c.published_at

    assert column.nullable is True


def test_outbox_created_at_is_required() -> None:
    column = OutboxEvent.__table__.c.created_at

    assert column.nullable is False
    assert column.server_default is not None


def test_outbox_has_publisher_polling_index() -> None:
    indexes = [
        index
        for index in OutboxEvent.__table__.indexes
        if isinstance(index, Index)
        and index.name == "ix_outbox_events_status_available_at_created_at"
    ]

    assert len(indexes) == 1

    index = indexes[0]

    assert [column.name for column in index.columns] == [
        "status",
        "available_at",
        "created_at",
    ]


def test_outbox_has_tenant_timeline_index() -> None:
    indexes = [
        index
        for index in OutboxEvent.__table__.indexes
        if isinstance(index, Index) and index.name == "ix_outbox_events_tenant_created_at"
    ]

    assert len(indexes) == 1

    index = indexes[0]

    assert [column.name for column in index.columns] == [
        "tenant_id",
        "created_at",
    ]


def test_outbox_has_aggregate_lookup_index() -> None:
    indexes = [
        index
        for index in OutboxEvent.__table__.indexes
        if isinstance(index, Index) and index.name == "ix_outbox_events_tenant_aggregate"
    ]

    assert len(indexes) == 1

    index = indexes[0]

    assert [column.name for column in index.columns] == [
        "tenant_id",
        "aggregate_type",
        "aggregate_id",
    ]


def test_outbox_does_not_store_broker_topology() -> None:
    column_names = set(
        OutboxEvent.__table__.c.keys(),
    )

    forbidden_columns = {
        "queue_name",
        "exchange_name",
        "routing_key",
    }

    assert column_names.isdisjoint(
        forbidden_columns,
    )


def test_outbox_does_not_store_secret_columns() -> None:
    column_names = set(
        OutboxEvent.__table__.c.keys(),
    )

    forbidden_columns = {
        "password",
        "access_token",
        "refresh_token",
        "client_secret",
        "api_key",
        "presigned_url",
    }

    assert column_names.isdisjoint(
        forbidden_columns,
    )
