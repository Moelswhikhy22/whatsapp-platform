from __future__ import annotations

from sqlalchemy import ForeignKeyConstraint, Index, UniqueConstraint

from app.db.models import Conversation


def test_conversation_table_name() -> None:
    assert Conversation.__tablename__ == "conversations"


def test_conversation_tenant_id_is_required() -> None:
    column = Conversation.__table__.c.tenant_id

    assert column.nullable is False


def test_conversation_tenant_id_is_indexed() -> None:
    column = Conversation.__table__.c.tenant_id

    assert column.index is True


def test_conversation_has_direct_tenant_foreign_key() -> None:
    column = Conversation.__table__.c.tenant_id

    foreign_keys = [
        foreign_key
        for foreign_key in column.foreign_keys
        if foreign_key.target_fullname == "tenants.id"
    ]

    assert len(foreign_keys) == 1
    assert foreign_keys[0].ondelete == "RESTRICT"


def test_conversation_whatsapp_number_is_required() -> None:
    column = Conversation.__table__.c.whatsapp_number_id

    assert column.nullable is False


def test_conversation_customer_contact_is_required() -> None:
    column = Conversation.__table__.c.customer_contact_id

    assert column.nullable is False


def test_conversation_group_is_optional_until_routed() -> None:
    column = Conversation.__table__.c.group_id

    assert column.nullable is True


def test_conversation_has_tenant_safe_candidate_key() -> None:
    constraints = [
        constraint
        for constraint in Conversation.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
        and constraint.name == "uq_conversations_tenant_id_id"
    ]

    assert len(constraints) == 1

    constraint = constraints[0]

    assert [column.name for column in constraint.columns] == [
        "tenant_id",
        "id",
    ]


def test_logical_conversation_is_unique_per_number_and_contact() -> None:
    constraints = [
        constraint
        for constraint in Conversation.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
        and constraint.name == "uq_conversations_tenant_number_contact"
    ]

    assert len(constraints) == 1

    constraint = constraints[0]

    assert [column.name for column in constraint.columns] == [
        "tenant_id",
        "whatsapp_number_id",
        "customer_contact_id",
    ]


def test_conversation_has_tenant_safe_whatsapp_number_fk() -> None:
    constraints = [
        constraint
        for constraint in Conversation.__table__.constraints
        if isinstance(constraint, ForeignKeyConstraint)
        and constraint.name == "fk_conversations_tenant_whatsapp_number"
    ]

    assert len(constraints) == 1

    constraint = constraints[0]

    assert [element.parent.name for element in constraint.elements] == [
        "tenant_id",
        "whatsapp_number_id",
    ]

    assert [element.target_fullname for element in constraint.elements] == [
        "whatsapp_numbers.tenant_id",
        "whatsapp_numbers.id",
    ]

    assert constraint.ondelete == "RESTRICT"


def test_conversation_has_tenant_safe_customer_contact_fk() -> None:
    constraints = [
        constraint
        for constraint in Conversation.__table__.constraints
        if isinstance(constraint, ForeignKeyConstraint)
        and constraint.name == "fk_conversations_tenant_customer_contact"
    ]

    assert len(constraints) == 1

    constraint = constraints[0]

    assert [element.parent.name for element in constraint.elements] == [
        "tenant_id",
        "customer_contact_id",
    ]

    assert [element.target_fullname for element in constraint.elements] == [
        "customer_contacts.tenant_id",
        "customer_contacts.id",
    ]

    assert constraint.ondelete == "RESTRICT"


def test_conversation_has_tenant_safe_group_fk() -> None:
    constraints = [
        constraint
        for constraint in Conversation.__table__.constraints
        if isinstance(constraint, ForeignKeyConstraint)
        and constraint.name == "fk_conversations_tenant_group"
    ]

    assert len(constraints) == 1

    constraint = constraints[0]

    assert [element.parent.name for element in constraint.elements] == [
        "tenant_id",
        "group_id",
    ]

    assert [element.target_fullname for element in constraint.elements] == [
        "groups.tenant_id",
        "groups.id",
    ]

    assert constraint.ondelete == "RESTRICT"


def test_conversation_has_group_lookup_index() -> None:
    indexes = [
        index
        for index in Conversation.__table__.indexes
        if isinstance(index, Index) and index.name == "ix_conversations_tenant_id_group_id"
    ]

    assert len(indexes) == 1

    index = indexes[0]

    assert [column.name for column in index.columns] == [
        "tenant_id",
        "group_id",
    ]


def test_conversation_has_customer_contact_lookup_index() -> None:
    indexes = [
        index
        for index in Conversation.__table__.indexes
        if isinstance(index, Index)
        and index.name == "ix_conversations_tenant_id_customer_contact_id"
    ]

    assert len(indexes) == 1

    index = indexes[0]

    assert [column.name for column in index.columns] == [
        "tenant_id",
        "customer_contact_id",
    ]


def test_conversation_does_not_duplicate_customer_company() -> None:
    column_names = set(
        Conversation.__table__.c.keys(),
    )

    assert "customer_company_id" not in column_names


def test_conversation_timestamps_are_required() -> None:
    created_at_column = Conversation.__table__.c.created_at
    updated_at_column = Conversation.__table__.c.updated_at

    assert created_at_column.nullable is False
    assert updated_at_column.nullable is False

    assert created_at_column.server_default is not None
    assert updated_at_column.server_default is not None
