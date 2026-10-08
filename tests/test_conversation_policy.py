from __future__ import annotations

from uuid import uuid4

from app.db.models.group import Group
from app.services.conversation_policy import (
    conversation_send_policy_from_group,
    conversation_visibility_policy_from_group,
)


def test_group_can_enable_team_read_after_claim() -> None:
    group = Group(
        tenant_id=uuid4(),
        name="Sales",
        team_read_after_claim=True,
    )

    policy = conversation_visibility_policy_from_group(
        group,
    )

    assert policy.team_read_after_claim is True


def test_group_can_disable_team_read_after_claim() -> None:
    group = Group(
        tenant_id=uuid4(),
        name="Sales",
        team_read_after_claim=False,
    )

    policy = conversation_visibility_policy_from_group(
        group,
    )

    assert policy.team_read_after_claim is False


def test_group_can_enable_non_owner_employee_send() -> None:
    group = Group(
        tenant_id=uuid4(),
        name="Sales",
        allow_non_owner_employee_send=True,
    )

    policy = conversation_send_policy_from_group(
        group,
    )

    assert policy.allow_non_owner_employee_send is True


def test_group_can_disable_non_owner_employee_send() -> None:
    group = Group(
        tenant_id=uuid4(),
        name="Sales",
        allow_non_owner_employee_send=False,
    )

    policy = conversation_send_policy_from_group(
        group,
    )

    assert policy.allow_non_owner_employee_send is False
