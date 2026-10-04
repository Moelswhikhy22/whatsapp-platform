from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    UniqueConstraint,
)

from app.db.models import MediaObject


def test_media_object_table_name() -> None:
    assert MediaObject.__tablename__ == "media_objects"


def test_media_object_tenant_id_is_required() -> None:
    column = MediaObject.__table__.c.tenant_id

    assert column.nullable is False


def test_media_object_tenant_id_is_indexed() -> None:
    column = MediaObject.__table__.c.tenant_id

    assert column.index is True


def test_media_object_has_direct_tenant_fk() -> None:
    column = MediaObject.__table__.c.tenant_id

    foreign_keys = [
        foreign_key
        for foreign_key in column.foreign_keys
        if foreign_key.target_fullname == "tenants.id"
    ]

    assert len(foreign_keys) == 1
    assert foreign_keys[0].ondelete == "RESTRICT"


def test_media_object_message_id_is_required() -> None:
    column = MediaObject.__table__.c.message_id

    assert column.nullable is False


def test_media_object_has_tenant_safe_message_fk() -> None:
    constraints = [
        constraint
        for constraint in MediaObject.__table__.constraints
        if isinstance(constraint, ForeignKeyConstraint)
        and constraint.name == "fk_media_objects_tenant_message"
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


def test_media_object_has_tenant_safe_candidate_key() -> None:
    constraints = [
        constraint
        for constraint in MediaObject.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
        and constraint.name == "uq_media_objects_tenant_id_id"
    ]

    assert len(constraints) == 1

    constraint = constraints[0]

    assert [column.name for column in constraint.columns] == [
        "tenant_id",
        "id",
    ]


def test_s3_object_location_is_globally_unique() -> None:
    constraints = [
        constraint
        for constraint in MediaObject.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
        and constraint.name == "uq_media_objects_bucket_object_key"
    ]

    assert len(constraints) == 1

    constraint = constraints[0]

    assert [column.name for column in constraint.columns] == [
        "bucket",
        "object_key",
    ]


def test_s3_location_fields_are_required() -> None:
    table = MediaObject.__table__

    assert table.c.bucket.nullable is False
    assert table.c.object_key.nullable is False


def test_original_filename_is_optional() -> None:
    column = MediaObject.__table__.c.original_filename

    assert column.nullable is True


def test_mime_type_is_required() -> None:
    column = MediaObject.__table__.c.mime_type

    assert column.nullable is False


def test_size_bytes_is_required() -> None:
    column = MediaObject.__table__.c.size_bytes

    assert column.nullable is False


def test_size_bytes_cannot_be_negative() -> None:
    constraints = [
        constraint
        for constraint in MediaObject.__table__.constraints
        if isinstance(constraint, CheckConstraint)
        and constraint.name == "ck_media_objects_size_bytes_non_negative"
    ]

    assert len(constraints) == 1


def test_sha256_is_required() -> None:
    column = MediaObject.__table__.c.sha256

    assert column.nullable is False


def test_retention_until_is_required() -> None:
    column = MediaObject.__table__.c.retention_until

    assert column.nullable is False


def test_deleted_at_is_optional() -> None:
    column = MediaObject.__table__.c.deleted_at

    assert column.nullable is True


def test_media_object_has_message_lookup_index() -> None:
    indexes = [
        index
        for index in MediaObject.__table__.indexes
        if isinstance(index, Index) and index.name == "ix_media_objects_tenant_id_message_id"
    ]

    assert len(indexes) == 1

    index = indexes[0]

    assert [column.name for column in index.columns] == [
        "tenant_id",
        "message_id",
    ]


def test_media_object_has_retention_lookup_index() -> None:
    indexes = [
        index
        for index in MediaObject.__table__.indexes
        if isinstance(index, Index) and index.name == "ix_media_objects_tenant_id_retention_until"
    ]

    assert len(indexes) == 1

    index = indexes[0]

    assert [column.name for column in index.columns] == [
        "tenant_id",
        "retention_until",
    ]


def test_media_object_created_at_is_required() -> None:
    column = MediaObject.__table__.c.created_at

    assert column.nullable is False
    assert column.server_default is not None


def test_media_object_does_not_store_binary_content() -> None:
    column_names = set(
        MediaObject.__table__.c.keys(),
    )

    forbidden_columns = {
        "data",
        "binary",
        "blob",
        "content",
        "file_bytes",
    }

    assert column_names.isdisjoint(
        forbidden_columns,
    )


def test_media_object_does_not_store_presigned_url() -> None:
    column_names = set(
        MediaObject.__table__.c.keys(),
    )

    forbidden_columns = {
        "url",
        "download_url",
        "presigned_url",
        "signed_url",
    }

    assert column_names.isdisjoint(
        forbidden_columns,
    )
