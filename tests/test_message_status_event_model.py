from __future__ import annotations

from sqlalchemy import ForeignKeyConstraint, Index, UniqueConstraint

from app.db.models import MessageStatusEvent


def test_message_status_event_table_name() -> None:
    assert MessageStatusEvent.__tablename__ == "message_status_events"


def test_message_status_event_tenant_id_is_required() -> None:
    column = MessageStatusEvent.__table__.c.tenant_id

    assert column.nullable is False


def test_message_status_event_tenant_id_is_indexed() -> None:
    column = MessageStatusEvent.__table__.c.tenant_id

    assert column.index is True


def test_message_status_event_has_direct_tenant_fk() -> None:
    column = MessageStatusEvent.__table__.c.tenant_id

    foreign_keys = [
        foreign_key
        for foreign_key in column.foreign_keys
        if foreign_key.target_fullname == "tenants.id"
    ]

    assert len(foreign_keys) == 1
    assert foreign_keys[0].ondelete == "RESTRICT"


def test_message_status_event_message_is_required() -> None:
    column = MessageStatusEvent.__table__.c.message_id

    assert column.nullable is False


def test_message_status_event_has_tenant_safe_message_fk() -> None:
    constraints = [
        constraint
        for constraint in MessageStatusEvent.__table__.constraints
        if isinstance(constraint, ForeignKeyConstraint)
        and constraint.name == "fk_message_status_events_tenant_message"
    ]

    assert len(constraints) == 1

    constraint = constraints[0]

    assert [element.parent.name for element in constraint.elements] == [
        "tenant_id",
        "message_id",
    ]

    assert [element.target_fullname for element in constraint.elements] == [
        "messages.tenant_id",
        "messages.id",
    ]

    assert constraint.ondelete == "RESTRICT"


def test_message_status_event_has_tenant_safe_candidate_key() -> None:
    constraints = [
        constraint
        for constraint in MessageStatusEvent.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
        and constraint.name == "uq_message_status_events_tenant_id_id"
    ]

    assert len(constraints) == 1

    constraint = constraints[0]

    assert [column.name for column in constraint.columns] == [
        "tenant_id",
        "id",
    ]


def test_message_status_is_required() -> None:
    column = MessageStatusEvent.__table__.c.status

    assert column.nullable is False


def test_message_status_event_meta_timestamp_is_optional() -> None:
    column = MessageStatusEvent.__table__.c.meta_timestamp

    assert column.nullable is True


def test_message_status_event_has_timeline_index() -> None:
    indexes = [
        index
        for index in MessageStatusEvent.__table__.indexes
        if isinstance(index, Index)
        and index.name == ("ix_message_status_events_tenant_message_created_at")
    ]

    assert len(indexes) == 1

    index = indexes[0]

    assert [column.name for column in index.columns] == [
        "tenant_id",
        "message_id",
        "created_at",
    ]


def test_message_status_event_created_at_is_required() -> None:
    column = MessageStatusEvent.__table__.c.created_at

    assert column.nullable is False
    assert column.server_default is not None


def test_message_status_event_is_append_only_shape() -> None:
    column_names = set(
        MessageStatusEvent.__table__.c.keys(),
    )

    assert "updated_at" not in column_names
    assert "active" not in column_names


def test_semantic_rank_is_deferred_to_status_worker() -> None:
    column_names = set(
        MessageStatusEvent.__table__.c.keys(),
    )

    assert "semantic_rank" not in column_names
