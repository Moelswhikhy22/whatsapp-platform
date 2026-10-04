from __future__ import annotations

from sqlalchemy import CheckConstraint, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB

from app.db.models import (
    RawWebhookEvent,
    RawWebhookProcessingStatus,
    RawWebhookProvider,
)


def test_raw_webhook_event_table_name() -> None:
    assert RawWebhookEvent.__tablename__ == "raw_webhook_events"


def test_raw_webhook_provider_values() -> None:
    assert {provider.value for provider in RawWebhookProvider} == {
        "meta",
    }


def test_raw_webhook_processing_status_values() -> None:
    assert {status.value for status in RawWebhookProcessingStatus} == {
        "received",
        "processing",
        "processed",
        "failed",
        "unresolved",
    }


def test_raw_webhook_tenant_id_is_optional_until_resolved() -> None:
    column = RawWebhookEvent.__table__.c.tenant_id

    assert column.nullable is True


def test_raw_webhook_has_optional_direct_tenant_fk() -> None:
    column = RawWebhookEvent.__table__.c.tenant_id

    foreign_keys = [
        foreign_key
        for foreign_key in column.foreign_keys
        if foreign_key.target_fullname == "tenants.id"
    ]

    assert len(foreign_keys) == 1
    assert foreign_keys[0].ondelete == "RESTRICT"


def test_raw_webhook_has_tenant_candidate_key() -> None:
    constraints = [
        constraint
        for constraint in RawWebhookEvent.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
        and constraint.name == "uq_raw_webhook_events_tenant_id_id"
    ]

    assert len(constraints) == 1

    constraint = constraints[0]

    assert [column.name for column in constraint.columns] == [
        "tenant_id",
        "id",
    ]


def test_raw_webhook_provider_is_required() -> None:
    column = RawWebhookEvent.__table__.c.provider

    assert column.nullable is False


def test_provider_event_key_is_required() -> None:
    column = RawWebhookEvent.__table__.c.provider_event_key

    assert column.nullable is False


def test_provider_event_key_is_unique_per_provider() -> None:
    constraints = [
        constraint
        for constraint in RawWebhookEvent.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
        and constraint.name == "uq_raw_webhook_events_provider_event_key"
    ]

    assert len(constraints) == 1

    constraint = constraints[0]

    assert [column.name for column in constraint.columns] == [
        "provider",
        "provider_event_key",
    ]


def test_event_type_is_optional() -> None:
    column = RawWebhookEvent.__table__.c.event_type

    assert column.nullable is True


def test_payload_json_is_required_and_uses_jsonb() -> None:
    column = RawWebhookEvent.__table__.c.payload_json

    assert column.nullable is False
    assert isinstance(
        column.type,
        JSONB,
    )


def test_processing_status_is_required_with_default() -> None:
    column = RawWebhookEvent.__table__.c.processing_status

    assert column.nullable is False
    assert column.server_default is not None


def test_attempts_is_required_with_default() -> None:
    column = RawWebhookEvent.__table__.c.attempts

    assert column.nullable is False
    assert column.server_default is not None


def test_attempts_cannot_be_negative() -> None:
    constraints = [
        constraint
        for constraint in RawWebhookEvent.__table__.constraints
        if isinstance(constraint, CheckConstraint)
        and constraint.name == "ck_raw_webhook_events_attempts_non_negative"
    ]

    assert len(constraints) == 1


def test_last_error_is_optional() -> None:
    column = RawWebhookEvent.__table__.c.last_error

    assert column.nullable is True


def test_received_at_is_required() -> None:
    column = RawWebhookEvent.__table__.c.received_at

    assert column.nullable is False
    assert column.server_default is not None


def test_processed_at_is_optional() -> None:
    column = RawWebhookEvent.__table__.c.processed_at

    assert column.nullable is True


def test_retention_until_is_optional() -> None:
    column = RawWebhookEvent.__table__.c.retention_until

    assert column.nullable is True


def test_raw_webhook_has_status_received_at_index() -> None:
    indexes = [
        index
        for index in RawWebhookEvent.__table__.indexes
        if isinstance(index, Index) and index.name == "ix_raw_webhook_events_status_received_at"
    ]

    assert len(indexes) == 1

    index = indexes[0]

    assert [column.name for column in index.columns] == [
        "processing_status",
        "received_at",
    ]


def test_raw_webhook_has_tenant_status_index() -> None:
    indexes = [
        index
        for index in RawWebhookEvent.__table__.indexes
        if isinstance(index, Index) and index.name == "ix_raw_webhook_events_tenant_status"
    ]

    assert len(indexes) == 1

    index = indexes[0]

    assert [column.name for column in index.columns] == [
        "tenant_id",
        "processing_status",
    ]


def test_raw_webhook_has_retention_index() -> None:
    indexes = [
        index
        for index in RawWebhookEvent.__table__.indexes
        if isinstance(index, Index) and index.name == "ix_raw_webhook_events_retention_until"
    ]

    assert len(indexes) == 1

    index = indexes[0]

    assert [column.name for column in index.columns] == [
        "retention_until",
    ]


def test_raw_webhook_has_no_active_or_updated_at_columns() -> None:
    column_names = set(
        RawWebhookEvent.__table__.c.keys(),
    )

    assert "active" not in column_names
    assert "updated_at" not in column_names
