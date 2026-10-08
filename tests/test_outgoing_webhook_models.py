from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.db.models import (
    OutgoingWebhookAttemptOutcome,
    OutgoingWebhookDelivery,
    OutgoingWebhookDeliveryAttempt,
    OutgoingWebhookDeliveryStatus,
    OutgoingWebhookSubscription,
)


def test_outgoing_webhook_subscription_table_name() -> None:
    assert OutgoingWebhookSubscription.__tablename__ == "outgoing_webhook_subscriptions"


def test_outgoing_webhook_delivery_table_name() -> None:
    assert OutgoingWebhookDelivery.__tablename__ == "outgoing_webhook_deliveries"


def test_outgoing_webhook_attempt_table_name() -> None:
    assert OutgoingWebhookDeliveryAttempt.__tablename__ == "outgoing_webhook_delivery_attempts"


def test_delivery_status_values() -> None:
    assert {status.value for status in OutgoingWebhookDeliveryStatus} == {
        "pending",
        "delivered",
        "failed",
    }


def test_attempt_outcome_values() -> None:
    assert {outcome.value for outcome in OutgoingWebhookAttemptOutcome} == {
        "succeeded",
        "failed",
    }


def test_subscription_tenant_is_required() -> None:
    column = OutgoingWebhookSubscription.__table__.c.tenant_id

    assert column.nullable is False
    assert column.index is True


def test_subscription_has_direct_tenant_fk() -> None:
    column = OutgoingWebhookSubscription.__table__.c.tenant_id

    foreign_keys = [
        foreign_key
        for foreign_key in column.foreign_keys
        if foreign_key.target_fullname == "tenants.id"
    ]

    assert len(foreign_keys) == 1
    assert foreign_keys[0].ondelete == "RESTRICT"


def test_subscription_has_tenant_safe_candidate_key() -> None:
    constraints = [
        constraint
        for constraint in OutgoingWebhookSubscription.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
        and constraint.name == ("uq_outgoing_webhook_subscriptions_tenant_id_id")
    ]

    assert len(constraints) == 1


def test_subscription_name_is_unique_inside_tenant() -> None:
    constraints = [
        constraint
        for constraint in OutgoingWebhookSubscription.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
        and constraint.name == ("uq_outgoing_webhook_subscriptions_tenant_name")
    ]

    assert len(constraints) == 1


def test_subscription_required_fields() -> None:
    table = OutgoingWebhookSubscription.__table__

    assert table.c.name.nullable is False
    assert table.c.endpoint_url.nullable is False
    assert table.c.event_types_json.nullable is False
    assert table.c.vault_secret_reference.nullable is False
    assert table.c.active.nullable is False


def test_subscription_event_types_use_jsonb() -> None:
    column = OutgoingWebhookSubscription.__table__.c.event_types_json

    assert isinstance(
        column.type,
        JSONB,
    )


def test_subscription_has_active_lookup_index() -> None:
    indexes = [
        index
        for index in OutgoingWebhookSubscription.__table__.indexes
        if isinstance(index, Index)
        and index.name == ("ix_outgoing_webhook_subscriptions_tenant_active")
    ]

    assert len(indexes) == 1


def test_delivery_tenant_is_required() -> None:
    column = OutgoingWebhookDelivery.__table__.c.tenant_id

    assert column.nullable is False
    assert column.index is True


def test_delivery_has_tenant_safe_subscription_fk() -> None:
    constraints = [
        constraint
        for constraint in OutgoingWebhookDelivery.__table__.constraints
        if isinstance(constraint, ForeignKeyConstraint)
        and constraint.name == ("fk_outgoing_webhook_deliveries_tenant_subscription")
    ]

    assert len(constraints) == 1

    constraint = constraints[0]

    assert [element.parent.name for element in constraint.elements] == [
        "tenant_id",
        "subscription_id",
    ]

    assert [element.target_fullname for element in constraint.elements] == [
        "outgoing_webhook_subscriptions.tenant_id",
        "outgoing_webhook_subscriptions.id",
    ]

    assert constraint.ondelete == "RESTRICT"


def test_delivery_is_unique_per_subscription_event() -> None:
    constraints = [
        constraint
        for constraint in OutgoingWebhookDelivery.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
        and constraint.name == ("uq_outgoing_webhook_deliveries_tenant_subscription_event")
    ]

    assert len(constraints) == 1


def test_delivery_event_fields_are_required() -> None:
    table = OutgoingWebhookDelivery.__table__

    assert table.c.event_id.nullable is False
    assert table.c.event_type.nullable is False
    assert table.c.payload_json.nullable is False

    assert isinstance(
        table.c.payload_json.type,
        JSONB,
    )


def test_delivery_status_has_default() -> None:
    column = OutgoingWebhookDelivery.__table__.c.status

    assert column.nullable is False
    assert column.server_default is not None


def test_delivery_attempt_count_has_default() -> None:
    column = OutgoingWebhookDelivery.__table__.c.attempt_count

    assert column.nullable is False
    assert column.server_default is not None


def test_delivery_attempt_count_cannot_be_negative() -> None:
    constraints = [
        constraint
        for constraint in OutgoingWebhookDelivery.__table__.constraints
        if isinstance(constraint, CheckConstraint)
        and constraint.name == ("ck_outgoing_webhook_deliveries_attempt_count_non_negative")
    ]

    assert len(constraints) == 1


def test_delivery_has_http_status_check() -> None:
    constraints = [
        constraint
        for constraint in OutgoingWebhookDelivery.__table__.constraints
        if isinstance(constraint, CheckConstraint)
        and constraint.name == ("ck_outgoing_webhook_deliveries_http_status_code")
    ]

    assert len(constraints) == 1


def test_delivery_has_delivered_state_check() -> None:
    constraints = [
        constraint
        for constraint in OutgoingWebhookDelivery.__table__.constraints
        if isinstance(constraint, CheckConstraint)
        and constraint.name == ("ck_outgoing_webhook_deliveries_delivered_state")
    ]

    assert len(constraints) == 1


def test_delivery_retry_fields() -> None:
    table = OutgoingWebhookDelivery.__table__

    assert table.c.next_attempt_at.nullable is False
    assert table.c.last_attempt_at.nullable is True
    assert table.c.last_http_status_code.nullable is True
    assert table.c.last_error.nullable is True
    assert table.c.delivered_at.nullable is True


def test_delivery_has_worker_polling_index() -> None:
    indexes = [
        index
        for index in OutgoingWebhookDelivery.__table__.indexes
        if isinstance(index, Index)
        and index.name == ("ix_outgoing_webhook_deliveries_status_next_attempt_created_at")
    ]

    assert len(indexes) == 1

    assert [column.name for column in indexes[0].columns] == [
        "status",
        "next_attempt_at",
        "created_at",
    ]


def test_delivery_has_subscription_history_index() -> None:
    indexes = [
        index
        for index in OutgoingWebhookDelivery.__table__.indexes
        if isinstance(index, Index)
        and index.name == ("ix_outgoing_webhook_deliveries_tenant_subscription_created_at")
    ]

    assert len(indexes) == 1


def test_attempt_tenant_is_required() -> None:
    column = OutgoingWebhookDeliveryAttempt.__table__.c.tenant_id

    assert column.nullable is False
    assert column.index is True


def test_attempt_has_tenant_safe_delivery_fk() -> None:
    constraints = [
        constraint
        for constraint in OutgoingWebhookDeliveryAttempt.__table__.constraints
        if isinstance(constraint, ForeignKeyConstraint)
        and constraint.name == ("fk_outgoing_webhook_delivery_attempts_tenant_delivery")
    ]

    assert len(constraints) == 1

    constraint = constraints[0]

    assert [element.parent.name for element in constraint.elements] == [
        "tenant_id",
        "delivery_id",
    ]

    assert [element.target_fullname for element in constraint.elements] == [
        "outgoing_webhook_deliveries.tenant_id",
        "outgoing_webhook_deliveries.id",
    ]


def test_attempt_number_is_unique_per_delivery() -> None:
    constraints = [
        constraint
        for constraint in OutgoingWebhookDeliveryAttempt.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
        and constraint.name == ("uq_outgoing_webhook_delivery_attempts_tenant_delivery_attempt")
    ]

    assert len(constraints) == 1


def test_attempt_number_must_be_positive() -> None:
    constraints = [
        constraint
        for constraint in OutgoingWebhookDeliveryAttempt.__table__.constraints
        if isinstance(constraint, CheckConstraint)
        and constraint.name == ("ck_outgoing_webhook_delivery_attempts_attempt_number_positive")
    ]

    assert len(constraints) == 1


def test_attempt_fields_are_required_or_optional_correctly() -> None:
    table = OutgoingWebhookDeliveryAttempt.__table__

    assert table.c.attempt_number.nullable is False
    assert table.c.outcome.nullable is False
    assert table.c.http_status_code.nullable is True
    assert table.c.error_message.nullable is True
    assert table.c.attempted_at.nullable is False


def test_attempt_history_is_append_only_shape() -> None:
    column_names = set(
        OutgoingWebhookDeliveryAttempt.__table__.c.keys(),
    )

    assert "updated_at" not in column_names
    assert "active" not in column_names
    assert "deleted_at" not in column_names


def test_subscription_does_not_store_signing_secret() -> None:
    column_names = set(
        OutgoingWebhookSubscription.__table__.c.keys(),
    )

    forbidden_columns = {
        "signing_secret",
        "secret",
        "hmac_secret",
        "webhook_secret",
    }

    assert column_names.isdisjoint(
        forbidden_columns,
    )


def test_delivery_attempt_does_not_store_response_body() -> None:
    column_names = set(
        OutgoingWebhookDeliveryAttempt.__table__.c.keys(),
    )

    assert "response_body" not in column_names
