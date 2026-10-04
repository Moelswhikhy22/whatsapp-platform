from __future__ import annotations

from sqlalchemy import ForeignKeyConstraint, Index, UniqueConstraint

from app.db.models import WhatsAppNumberGroup


def test_whatsapp_number_group_table_name() -> None:
    assert WhatsAppNumberGroup.__tablename__ == "whatsapp_number_groups"


def test_whatsapp_number_group_tenant_id_is_required() -> None:
    column = WhatsAppNumberGroup.__table__.c.tenant_id

    assert column.nullable is False


def test_whatsapp_number_group_tenant_id_is_indexed() -> None:
    column = WhatsAppNumberGroup.__table__.c.tenant_id

    assert column.index is True


def test_whatsapp_number_group_has_direct_tenant_foreign_key() -> None:
    column = WhatsAppNumberGroup.__table__.c.tenant_id

    foreign_keys = [
        foreign_key
        for foreign_key in column.foreign_keys
        if foreign_key.target_fullname == "tenants.id"
    ]

    assert len(foreign_keys) == 1
    assert foreign_keys[0].ondelete == "RESTRICT"


def test_whatsapp_number_id_is_required() -> None:
    column = WhatsAppNumberGroup.__table__.c.whatsapp_number_id

    assert column.nullable is False


def test_group_id_is_required() -> None:
    column = WhatsAppNumberGroup.__table__.c.group_id

    assert column.nullable is False


def test_whatsapp_number_group_has_tenant_safe_number_fk() -> None:
    constraints = [
        constraint
        for constraint in WhatsAppNumberGroup.__table__.constraints
        if isinstance(constraint, ForeignKeyConstraint)
        and constraint.name == "fk_whatsapp_number_groups_tenant_number"
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


def test_whatsapp_number_group_has_tenant_safe_group_fk() -> None:
    constraints = [
        constraint
        for constraint in WhatsAppNumberGroup.__table__.constraints
        if isinstance(constraint, ForeignKeyConstraint)
        and constraint.name == "fk_whatsapp_number_groups_tenant_group"
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


def test_whatsapp_number_group_has_tenant_safe_candidate_key() -> None:
    constraints = [
        constraint
        for constraint in WhatsAppNumberGroup.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
        and constraint.name == "uq_whatsapp_number_groups_tenant_id_id"
    ]

    assert len(constraints) == 1

    constraint = constraints[0]

    assert [column.name for column in constraint.columns] == [
        "tenant_id",
        "id",
    ]


def test_number_group_pair_is_unique_inside_tenant() -> None:
    constraints = [
        constraint
        for constraint in WhatsAppNumberGroup.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
        and constraint.name == ("uq_whatsapp_number_groups_tenant_id_whatsapp_number_id_group_id")
    ]

    assert len(constraints) == 1

    constraint = constraints[0]

    assert [column.name for column in constraint.columns] == [
        "tenant_id",
        "whatsapp_number_id",
        "group_id",
    ]


def test_whatsapp_number_group_has_group_lookup_index() -> None:
    indexes = [
        index
        for index in WhatsAppNumberGroup.__table__.indexes
        if isinstance(index, Index) and index.name == "ix_whatsapp_number_groups_tenant_id_group_id"
    ]

    assert len(indexes) == 1

    index = indexes[0]

    assert [column.name for column in index.columns] == [
        "tenant_id",
        "group_id",
    ]


def test_whatsapp_number_group_active_defaults_to_true() -> None:
    column = WhatsAppNumberGroup.__table__.c.active

    assert column.nullable is False
    assert column.server_default is not None


def test_whatsapp_number_group_timestamps_are_required() -> None:
    created_at_column = WhatsAppNumberGroup.__table__.c.created_at
    updated_at_column = WhatsAppNumberGroup.__table__.c.updated_at

    assert created_at_column.nullable is False
    assert updated_at_column.nullable is False

    assert created_at_column.server_default is not None
    assert updated_at_column.server_default is not None
