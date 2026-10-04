from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.db.models import (
    Template,
    TemplateStatus,
    TemplateType,
)


def test_template_table_name() -> None:
    assert Template.__tablename__ == "templates"


def test_template_type_values() -> None:
    assert {template_type.value for template_type in TemplateType} == {
        "internal",
        "meta",
    }


def test_template_status_values() -> None:
    assert {status.value for status in TemplateStatus} == {
        "draft",
        "submitted",
        "approved",
        "rejected",
        "paused",
        "disabled",
    }


def test_template_tenant_id_is_required() -> None:
    column = Template.__table__.c.tenant_id

    assert column.nullable is False


def test_template_tenant_id_is_indexed() -> None:
    column = Template.__table__.c.tenant_id

    assert column.index is True


def test_template_has_direct_tenant_fk() -> None:
    column = Template.__table__.c.tenant_id

    foreign_keys = [
        foreign_key
        for foreign_key in column.foreign_keys
        if foreign_key.target_fullname == "tenants.id"
    ]

    assert len(foreign_keys) == 1
    assert foreign_keys[0].ondelete == "RESTRICT"


def test_template_has_tenant_safe_candidate_key() -> None:
    constraints = [
        constraint
        for constraint in Template.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
        and constraint.name == "uq_templates_tenant_id_id"
    ]

    assert len(constraints) == 1

    constraint = constraints[0]

    assert [column.name for column in constraint.columns] == [
        "tenant_id",
        "id",
    ]


def test_internal_template_name_is_unique_inside_tenant() -> None:
    constraints = [
        constraint
        for constraint in Template.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
        and constraint.name == "uq_templates_tenant_internal_name"
    ]

    assert len(constraints) == 1

    constraint = constraints[0]

    assert [column.name for column in constraint.columns] == [
        "tenant_id",
        "name",
    ]


def test_meta_template_identity_is_unique_inside_account() -> None:
    constraints = [
        constraint
        for constraint in Template.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
        and constraint.name == "uq_templates_tenant_meta_account_name_language"
    ]

    assert len(constraints) == 1

    constraint = constraints[0]

    assert [column.name for column in constraint.columns] == [
        "tenant_id",
        "meta_account_id",
        "meta_template_name",
        "language",
    ]


def test_template_type_is_required() -> None:
    column = Template.__table__.c.template_type

    assert column.nullable is False


def test_template_category_is_required() -> None:
    column = Template.__table__.c.category

    assert column.nullable is False


def test_internal_specific_columns_are_nullable_at_column_level() -> None:
    table = Template.__table__

    assert table.c.name.nullable is True
    assert table.c.body.nullable is True
    assert table.c.variables_json.nullable is True
    assert table.c.active.nullable is True


def test_meta_specific_columns_are_nullable_at_column_level() -> None:
    table = Template.__table__

    assert table.c.meta_template_name.nullable is True
    assert table.c.language.nullable is True
    assert table.c.components_json.nullable is True
    assert table.c.status.nullable is True
    assert table.c.meta_account_id.nullable is True
    assert table.c.last_synced_at.nullable is True


def test_template_uses_jsonb_for_structured_fields() -> None:
    table = Template.__table__

    assert isinstance(
        table.c.variables_json.type,
        JSONB,
    )

    assert isinstance(
        table.c.components_json.type,
        JSONB,
    )


def test_template_has_type_specific_shape_check() -> None:
    constraints = [
        constraint
        for constraint in Template.__table__.constraints
        if isinstance(constraint, CheckConstraint)
        and constraint.name == "ck_templates_type_specific_shape"
    ]

    assert len(constraints) == 1


def test_template_has_tenant_safe_meta_account_fk() -> None:
    constraints = [
        constraint
        for constraint in Template.__table__.constraints
        if isinstance(constraint, ForeignKeyConstraint)
        and constraint.name == "fk_templates_tenant_meta_account"
    ]

    assert len(constraints) == 1

    constraint = constraints[0]

    assert [element.parent.name for element in constraint.elements] == [
        "tenant_id",
        "meta_account_id",
    ]

    assert [element.target_fullname for element in constraint.elements] == [
        "integrations.tenant_id",
        "integrations.id",
    ]

    assert constraint.ondelete == "RESTRICT"


def test_template_has_type_lookup_index() -> None:
    indexes = [
        index
        for index in Template.__table__.indexes
        if isinstance(index, Index) and index.name == "ix_templates_tenant_id_template_type"
    ]

    assert len(indexes) == 1

    index = indexes[0]

    assert [column.name for column in index.columns] == [
        "tenant_id",
        "template_type",
    ]


def test_template_timestamps_are_required() -> None:
    created_at_column = Template.__table__.c.created_at
    updated_at_column = Template.__table__.c.updated_at

    assert created_at_column.nullable is False
    assert updated_at_column.nullable is False

    assert created_at_column.server_default is not None
    assert updated_at_column.server_default is not None
