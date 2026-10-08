from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    UniqueConstraint,
)

from app.db.models import (
    ConversationAssignmentHistory,
    ConversationAssignmentReason,
)


def test_assignment_history_table_name() -> None:
    assert ConversationAssignmentHistory.__tablename__ == "conversation_assignment_history"


def test_assignment_reason_values() -> None:
    assert {reason.value for reason in ConversationAssignmentReason} == {
        "claim",
        "reassignment",
        "return_to_queue",
        "auto_reassignment",
    }


def test_assignment_history_tenant_id_is_required() -> None:
    column = ConversationAssignmentHistory.__table__.c.tenant_id

    assert column.nullable is False


def test_assignment_history_tenant_id_is_indexed() -> None:
    column = ConversationAssignmentHistory.__table__.c.tenant_id

    assert column.index is True


def test_assignment_history_has_direct_tenant_fk() -> None:
    column = ConversationAssignmentHistory.__table__.c.tenant_id

    foreign_keys = [
        foreign_key
        for foreign_key in column.foreign_keys
        if foreign_key.target_fullname == "tenants.id"
    ]

    assert len(foreign_keys) == 1
    assert foreign_keys[0].ondelete == "RESTRICT"


def test_assignment_history_conversation_is_required() -> None:
    column = ConversationAssignmentHistory.__table__.c.conversation_id

    assert column.nullable is False


def test_assignment_history_has_tenant_safe_conversation_fk() -> None:
    constraints = [
        constraint
        for constraint in ConversationAssignmentHistory.__table__.constraints
        if isinstance(constraint, ForeignKeyConstraint)
        and constraint.name == ("fk_conversation_assignment_history_tenant_conversation")
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


def test_previous_employee_is_optional() -> None:
    column = ConversationAssignmentHistory.__table__.c.previous_employee_id

    assert column.nullable is True


def test_new_employee_is_optional() -> None:
    column = ConversationAssignmentHistory.__table__.c.new_employee_id

    assert column.nullable is True


def test_assignment_history_has_tenant_safe_previous_employee_fk() -> None:
    constraints = [
        constraint
        for constraint in ConversationAssignmentHistory.__table__.constraints
        if isinstance(constraint, ForeignKeyConstraint)
        and constraint.name == ("fk_conversation_assignment_history_tenant_previous_employee")
    ]

    assert len(constraints) == 1

    constraint = constraints[0]

    assert [element.parent.name for element in constraint.elements] == [
        "tenant_id",
        "previous_employee_id",
    ]

    assert [element.target_fullname for element in constraint.elements] == [
        "employees.tenant_id",
        "employees.id",
    ]

    assert constraint.ondelete == "RESTRICT"


def test_assignment_history_has_tenant_safe_new_employee_fk() -> None:
    constraints = [
        constraint
        for constraint in ConversationAssignmentHistory.__table__.constraints
        if isinstance(constraint, ForeignKeyConstraint)
        and constraint.name == ("fk_conversation_assignment_history_tenant_new_employee")
    ]

    assert len(constraints) == 1

    constraint = constraints[0]

    assert [element.parent.name for element in constraint.elements] == [
        "tenant_id",
        "new_employee_id",
    ]

    assert [element.target_fullname for element in constraint.elements] == [
        "employees.tenant_id",
        "employees.id",
    ]

    assert constraint.ondelete == "RESTRICT"


def test_assignment_history_has_tenant_safe_candidate_key() -> None:
    constraints = [
        constraint
        for constraint in ConversationAssignmentHistory.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
        and constraint.name == ("uq_conversation_assignment_history_tenant_id_id")
    ]

    assert len(constraints) == 1

    constraint = constraints[0]

    assert [column.name for column in constraint.columns] == [
        "tenant_id",
        "id",
    ]


def test_assignment_reason_is_required() -> None:
    column = ConversationAssignmentHistory.__table__.c.reason

    assert column.nullable is False


def test_assignment_history_requires_actual_owner_change() -> None:
    constraints = [
        constraint
        for constraint in ConversationAssignmentHistory.__table__.constraints
        if isinstance(constraint, CheckConstraint)
        and constraint.name == ("ck_conversation_assignment_history_employee_changed")
    ]

    assert len(constraints) == 1


def test_assignment_history_has_conversation_time_index() -> None:
    indexes = [
        index
        for index in ConversationAssignmentHistory.__table__.indexes
        if isinstance(index, Index)
        and index.name == ("ix_conversation_assignment_tenant_conversation_created_at")
    ]

    assert len(indexes) == 1

    index = indexes[0]

    assert [column.name for column in index.columns] == [
        "tenant_id",
        "conversation_id",
        "created_at",
    ]


def test_assignment_history_created_at_is_required() -> None:
    column = ConversationAssignmentHistory.__table__.c.created_at

    assert column.nullable is False
    assert column.server_default is not None


def test_assignment_history_is_append_only_shape() -> None:
    column_names = set(
        ConversationAssignmentHistory.__table__.c.keys(),
    )

    assert "updated_at" not in column_names
    assert "active" not in column_names
