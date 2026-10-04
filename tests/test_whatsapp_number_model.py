from __future__ import annotations

from sqlalchemy import ForeignKeyConstraint, UniqueConstraint

from app.db.models import WhatsAppNumber


def test_whatsapp_number_table_name() -> None:
    assert WhatsAppNumber.__tablename__ == "whatsapp_numbers"


def test_whatsapp_number_tenant_id_is_required() -> None:
    tenant_column = WhatsAppNumber.__table__.c.tenant_id

    assert tenant_column.nullable is False


def test_whatsapp_number_tenant_id_is_indexed() -> None:
    tenant_column = WhatsAppNumber.__table__.c.tenant_id

    assert tenant_column.index is True


def test_whatsapp_number_has_direct_tenant_foreign_key() -> None:
    tenant_column = WhatsAppNumber.__table__.c.tenant_id

    foreign_keys = [
        foreign_key
        for foreign_key in tenant_column.foreign_keys
        if foreign_key.target_fullname == "tenants.id"
    ]

    assert len(foreign_keys) == 1
    assert foreign_keys[0].ondelete == "RESTRICT"


def test_whatsapp_number_integration_id_is_required() -> None:
    integration_column = WhatsAppNumber.__table__.c.integration_id

    assert integration_column.nullable is False


def test_whatsapp_number_has_tenant_safe_integration_foreign_key() -> None:
    constraints = [
        constraint
        for constraint in WhatsAppNumber.__table__.constraints
        if isinstance(constraint, ForeignKeyConstraint)
        and constraint.name == "fk_whatsapp_numbers_tenant_integration"
    ]

    assert len(constraints) == 1

    constraint = constraints[0]

    assert [element.parent.name for element in constraint.elements] == [
        "tenant_id",
        "integration_id",
    ]

    assert [element.target_fullname for element in constraint.elements] == [
        "integrations.tenant_id",
        "integrations.id",
    ]

    assert constraint.ondelete == "RESTRICT"


def test_whatsapp_number_has_tenant_safe_candidate_key() -> None:
    constraints = [
        constraint
        for constraint in WhatsAppNumber.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
        and constraint.name == "uq_whatsapp_numbers_tenant_id_id"
    ]

    assert len(constraints) == 1

    constraint = constraints[0]

    assert [column.name for column in constraint.columns] == [
        "tenant_id",
        "id",
    ]


def test_meta_phone_number_id_is_required() -> None:
    column = WhatsAppNumber.__table__.c.meta_phone_number_id

    assert column.nullable is False


def test_meta_phone_number_id_is_globally_unique() -> None:
    constraints = [
        constraint
        for constraint in WhatsAppNumber.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
        and constraint.name == "uq_whatsapp_numbers_meta_phone_number_id"
    ]

    assert len(constraints) == 1

    constraint = constraints[0]

    assert [column.name for column in constraint.columns] == [
        "meta_phone_number_id",
    ]


def test_display_phone_number_is_required() -> None:
    column = WhatsAppNumber.__table__.c.display_phone_number

    assert column.nullable is False


def test_whatsapp_number_active_defaults_to_true() -> None:
    active_column = WhatsAppNumber.__table__.c.active

    assert active_column.nullable is False
    assert active_column.server_default is not None


def test_whatsapp_number_timestamps_are_required() -> None:
    created_at_column = WhatsAppNumber.__table__.c.created_at
    updated_at_column = WhatsAppNumber.__table__.c.updated_at

    assert created_at_column.nullable is False
    assert updated_at_column.nullable is False

    assert created_at_column.server_default is not None
    assert updated_at_column.server_default is not None
