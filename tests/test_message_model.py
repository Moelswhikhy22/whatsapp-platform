from __future__ import annotations

from sqlalchemy import ForeignKeyConstraint, Index, UniqueConstraint

from app.db.models import (
    Message,
    MessageDirection,
    MessageStatus,
    MessageType,
)


def test_message_table_name() -> None:
    assert Message.__tablename__ == "messages"


def test_message_direction_values() -> None:
    assert {direction.value for direction in MessageDirection} == {
        "inbound",
        "outbound",
    }


def test_message_type_values() -> None:
    assert {message_type.value for message_type in MessageType} == {
        "text",
        "image",
        "document",
        "audio",
        "video",
        "template",
    }


def test_message_status_values() -> None:
    assert {status.value for status in MessageStatus} == {
        "pending",
        "sent",
        "delivered",
        "read",
        "failed",
    }


def test_message_tenant_id_is_required() -> None:
    column = Message.__table__.c.tenant_id

    assert column.nullable is False


def test_message_tenant_id_is_indexed() -> None:
    column = Message.__table__.c.tenant_id

    assert column.index is True


def test_message_has_direct_tenant_foreign_key() -> None:
    column = Message.__table__.c.tenant_id

    foreign_keys = [
        foreign_key
        for foreign_key in column.foreign_keys
        if foreign_key.target_fullname == "tenants.id"
    ]

    assert len(foreign_keys) == 1
    assert foreign_keys[0].ondelete == "RESTRICT"


def test_message_conversation_is_required() -> None:
    column = Message.__table__.c.conversation_id

    assert column.nullable is False


def test_message_has_tenant_safe_conversation_fk() -> None:
    constraints = [
        constraint
        for constraint in Message.__table__.constraints
        if isinstance(constraint, ForeignKeyConstraint)
        and constraint.name == "fk_messages_tenant_conversation"
    ]

    assert len(constraints) == 1

    constraint = constraints[0]

    assert [element.parent.name for element in constraint.elements] == [
        "tenant_id",
        "conversation_id",
    ]

    assert [element.target_fullname for element in constraint.elements] == [
        "conversations.tenant_id",
        "conversations.id",
    ]

    assert constraint.ondelete == "RESTRICT"


def test_message_has_tenant_safe_candidate_key() -> None:
    constraints = [
        constraint
        for constraint in Message.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
        and constraint.name == "uq_messages_tenant_id_id"
    ]

    assert len(constraints) == 1

    constraint = constraints[0]

    assert [column.name for column in constraint.columns] == [
        "tenant_id",
        "id",
    ]


def test_meta_message_id_is_optional() -> None:
    column = Message.__table__.c.meta_message_id

    assert column.nullable is True


def test_meta_message_id_is_unique_inside_tenant() -> None:
    constraints = [
        constraint
        for constraint in Message.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
        and constraint.name == "uq_messages_tenant_id_meta_message_id"
    ]

    assert len(constraints) == 1

    constraint = constraints[0]

    assert [column.name for column in constraint.columns] == [
        "tenant_id",
        "meta_message_id",
    ]


def test_message_direction_is_required() -> None:
    column = Message.__table__.c.direction

    assert column.nullable is False


def test_message_type_is_required() -> None:
    column = Message.__table__.c.message_type

    assert column.nullable is False


def test_message_body_text_is_optional() -> None:
    column = Message.__table__.c.body_text

    assert column.nullable is True


def test_actual_actor_is_optional() -> None:
    column = Message.__table__.c.actual_actor_id

    assert column.nullable is True


def test_represented_employee_is_optional() -> None:
    column = Message.__table__.c.represented_employee_id

    assert column.nullable is True


def test_message_has_tenant_safe_actual_actor_fk() -> None:
    constraints = [
        constraint
        for constraint in Message.__table__.constraints
        if isinstance(constraint, ForeignKeyConstraint)
        and constraint.name == "fk_messages_tenant_actual_actor"
    ]

    assert len(constraints) == 1

    constraint = constraints[0]

    assert [element.parent.name for element in constraint.elements] == [
        "tenant_id",
        "actual_actor_id",
    ]

    assert [element.target_fullname for element in constraint.elements] == [
        "employees.tenant_id",
        "employees.id",
    ]

    assert constraint.ondelete == "RESTRICT"


def test_message_has_tenant_safe_represented_employee_fk() -> None:
    constraints = [
        constraint
        for constraint in Message.__table__.constraints
        if isinstance(constraint, ForeignKeyConstraint)
        and constraint.name == "fk_messages_tenant_represented_employee"
    ]

    assert len(constraints) == 1

    constraint = constraints[0]

    assert [element.parent.name for element in constraint.elements] == [
        "tenant_id",
        "represented_employee_id",
    ]

    assert [element.target_fullname for element in constraint.elements] == [
        "employees.tenant_id",
        "employees.id",
    ]

    assert constraint.ondelete == "RESTRICT"


def test_external_actor_id_is_optional() -> None:
    column = Message.__table__.c.external_actor_id

    assert column.nullable is True


def test_message_status_is_optional() -> None:
    column = Message.__table__.c.status

    assert column.nullable is True


def test_meta_timestamp_is_optional() -> None:
    column = Message.__table__.c.meta_timestamp

    assert column.nullable is True


def test_message_has_conversation_timeline_index() -> None:
    indexes = [
        index
        for index in Message.__table__.indexes
        if isinstance(index, Index)
        and index.name == "ix_messages_tenant_id_conversation_created_at"
    ]

    assert len(indexes) == 1

    index = indexes[0]

    assert [column.name for column in index.columns] == [
        "tenant_id",
        "conversation_id",
        "created_at",
    ]


def test_message_created_at_is_required() -> None:
    column = Message.__table__.c.created_at

    assert column.nullable is False
    assert column.server_default is not None


def test_message_source_and_attribution_are_persisted() -> None:
    column_names = set(
        Message.__table__.c.keys(),
    )

    assert "source" in column_names
    assert "actor_attribution" in column_names

    source_column = Message.__table__.c.source
    attribution_column = Message.__table__.c.actor_attribution

    assert source_column.nullable is False
    assert attribution_column.nullable is False

    assert set(source_column.type.enums) == {
        "meta",
        "platform",
        "odoo",
        "integration",
        "whatsapp_external",
        "unknown",
    }

    assert set(attribution_column.type.enums) == {
        "exact",
        "represented",
        "external",
        "unknown",
    }