from __future__ import annotations

from uuid import UUID

from app.authorization.context import AuthorizationContext
from app.authorization.conversation import (
    ConversationAccessResource,
    ConversationActorContext,
    can_claim_conversation,
)
from app.authorization.roles import Role

TENANT_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

GROUP_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")

OTHER_GROUP_ID = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

EMPLOYEE_ID = UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")


def _queued_conversation() -> ConversationAccessResource:
    return ConversationAccessResource(
        tenant_id=TENANT_ID,
        group_id=GROUP_ID,
        responsible_employee_id=None,
        is_queued=True,
    )


def test_employee_group_admin_multirole_can_claim_as_member() -> None:
    context = AuthorizationContext(
        actor_id="keycloak-user-123",
        tenant_id=TENANT_ID,
        roles=frozenset(
            {
                Role.EMPLOYEE,
                Role.GROUP_ADMIN,
            }
        ),
    )

    actor = ConversationActorContext(
        employee_id=EMPLOYEE_ID,
        member_group_ids=frozenset(
            {
                GROUP_ID,
            }
        ),
        administered_group_ids=frozenset(),
    )

    assert can_claim_conversation(
        context,
        actor,
        _queued_conversation(),
    )


def test_tenant_admin_employee_multirole_can_claim_as_member() -> None:
    context = AuthorizationContext(
        actor_id="keycloak-user-123",
        tenant_id=TENANT_ID,
        roles=frozenset(
            {
                Role.TENANT_ADMIN,
                Role.EMPLOYEE,
            }
        ),
    )

    actor = ConversationActorContext(
        employee_id=EMPLOYEE_ID,
        member_group_ids=frozenset(
            {
                GROUP_ID,
            }
        ),
    )

    assert can_claim_conversation(
        context,
        actor,
        _queued_conversation(),
    )


def test_group_admin_can_claim_administered_member_group() -> None:
    context = AuthorizationContext(
        actor_id="keycloak-user-123",
        tenant_id=TENANT_ID,
        roles=frozenset(
            {
                Role.GROUP_ADMIN,
            }
        ),
    )

    actor = ConversationActorContext(
        employee_id=EMPLOYEE_ID,
        member_group_ids=frozenset(
            {
                GROUP_ID,
            }
        ),
        administered_group_ids=frozenset(
            {
                GROUP_ID,
            }
        ),
    )

    assert can_claim_conversation(
        context,
        actor,
        _queued_conversation(),
    )


def test_group_admin_cannot_claim_non_administered_group() -> None:
    context = AuthorizationContext(
        actor_id="keycloak-user-123",
        tenant_id=TENANT_ID,
        roles=frozenset(
            {
                Role.GROUP_ADMIN,
            }
        ),
    )

    actor = ConversationActorContext(
        employee_id=EMPLOYEE_ID,
        member_group_ids=frozenset(
            {
                GROUP_ID,
            }
        ),
        administered_group_ids=frozenset(
            {
                OTHER_GROUP_ID,
            }
        ),
    )

    assert not can_claim_conversation(
        context,
        actor,
        _queued_conversation(),
    )


def test_multirole_actor_cannot_claim_without_group_membership() -> None:
    context = AuthorizationContext(
        actor_id="keycloak-user-123",
        tenant_id=TENANT_ID,
        roles=frozenset(
            {
                Role.TENANT_ADMIN,
                Role.GROUP_ADMIN,
                Role.EMPLOYEE,
            }
        ),
    )

    actor = ConversationActorContext(
        employee_id=EMPLOYEE_ID,
        member_group_ids=frozenset(),
        administered_group_ids=frozenset(
            {
                GROUP_ID,
            }
        ),
    )

    assert not can_claim_conversation(
        context,
        actor,
        _queued_conversation(),
    )
