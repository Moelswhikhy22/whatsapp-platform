from sqlalchemy import ForeignKeyConstraint

from app.db.models.conversation import (
    Conversation,
    ConversationState,
)
from app.db.models.group import Group


def test_conversation_state_values() -> None:
    assert [state.value for state in ConversationState] == [
        "queued",
        "claimed",
        "open",
        "waiting_customer",
        "waiting_team",
        "closed",
        "reopened",
    ]


def test_conversation_state_defaults_to_queued() -> None:
    column = Conversation.__table__.c.state

    assert column.nullable is False
    assert column.default is not None
    assert column.default.arg == ConversationState.QUEUED
    assert column.server_default is not None
    assert "queued" in str(column.server_default.arg)


def test_conversation_has_nullable_responsible_employee() -> None:
    column = Conversation.__table__.c.responsible_employee_id

    assert column.nullable is True


def test_conversation_has_nullable_claimed_at() -> None:
    column = Conversation.__table__.c.claimed_at

    assert column.nullable is True


def test_responsible_employee_fk_is_tenant_safe() -> None:
    constraint = next(
        constraint
        for constraint in Conversation.__table__.constraints
        if isinstance(constraint, ForeignKeyConstraint)
        and constraint.name == "fk_conversations_tenant_responsible_employee"
    )

    assert [element.parent.name for element in constraint.elements] == [
        "tenant_id",
        "responsible_employee_id",
    ]

    assert [element.target_fullname for element in constraint.elements] == [
        "employees.tenant_id",
        "employees.id",
    ]

    assert constraint.ondelete == "RESTRICT"


def test_group_claim_on_open_defaults_false() -> None:
    column = Group.__table__.c.claim_on_open

    assert column.nullable is False
    assert column.default is not None
    assert column.default.arg is False
    assert column.server_default is not None
    assert "false" in str(column.server_default.arg).lower()
