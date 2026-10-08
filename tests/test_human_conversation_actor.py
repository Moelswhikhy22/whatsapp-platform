from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.db.models.employee import Employee
from app.db.models.group_membership import GroupMembership
from app.repositories.external_identity import ExternalIdentityRepository
from app.repositories.group_membership import GroupMembershipRepository
from app.services.human_conversation_actor import (
    KEYCLOAK_IDENTITY_PROVIDER,
    HumanConversationActorResolver,
)

SUBJECT = "keycloak-user-123"


@pytest.mark.asyncio
async def test_resolves_employee_and_group_relationships() -> None:
    employee_id = uuid4()
    tenant_id = uuid4()
    member_group_id = uuid4()
    administered_group_id = uuid4()

    employee = Employee(
        id=employee_id,
        tenant_id=tenant_id,
        display_name="Ahmed",
        active=True,
    )

    external_identity_repository = AsyncMock(
        spec=ExternalIdentityRepository,
    )

    group_membership_repository = AsyncMock(
        spec=GroupMembershipRepository,
    )

    external_identity_repository.get_active_employee_by_provider_user.return_value = employee

    group_membership_repository.list_active_for_employee.return_value = [
        GroupMembership(
            tenant_id=tenant_id,
            group_id=member_group_id,
            employee_id=employee_id,
            is_admin=False,
            active=True,
        ),
        GroupMembership(
            tenant_id=tenant_id,
            group_id=administered_group_id,
            employee_id=employee_id,
            is_admin=True,
            active=True,
        ),
    ]

    resolver = HumanConversationActorResolver(
        external_identity_repository=external_identity_repository,
        group_membership_repository=group_membership_repository,
    )

    actor = await resolver.resolve(
        subject=SUBJECT,
    )

    assert actor.employee_id == employee_id

    assert actor.member_group_ids == frozenset(
        {
            member_group_id,
            administered_group_id,
        }
    )

    assert actor.administered_group_ids == frozenset(
        {
            administered_group_id,
        }
    )

    external_identity_repository.get_active_employee_by_provider_user.assert_awaited_once_with(
        provider=KEYCLOAK_IDENTITY_PROVIDER,
        external_user_id=SUBJECT,
    )

    group_membership_repository.list_active_for_employee.assert_awaited_once_with(
        employee_id,
    )


@pytest.mark.asyncio
async def test_missing_employee_mapping_returns_empty_actor_context() -> None:
    external_identity_repository = AsyncMock(
        spec=ExternalIdentityRepository,
    )

    group_membership_repository = AsyncMock(
        spec=GroupMembershipRepository,
    )

    external_identity_repository.get_active_employee_by_provider_user.return_value = None

    resolver = HumanConversationActorResolver(
        external_identity_repository=external_identity_repository,
        group_membership_repository=group_membership_repository,
    )

    actor = await resolver.resolve(
        subject=SUBJECT,
    )

    assert actor.employee_id is None
    assert actor.member_group_ids == frozenset()
    assert actor.administered_group_ids == frozenset()

    group_membership_repository.list_active_for_employee.assert_not_awaited()


@pytest.mark.asyncio
async def test_employee_without_group_memberships_has_employee_identity() -> None:
    employee_id = uuid4()

    employee = Employee(
        id=employee_id,
        tenant_id=uuid4(),
        display_name="Ahmed",
        active=True,
    )

    external_identity_repository = AsyncMock(
        spec=ExternalIdentityRepository,
    )

    group_membership_repository = AsyncMock(
        spec=GroupMembershipRepository,
    )

    external_identity_repository.get_active_employee_by_provider_user.return_value = employee

    group_membership_repository.list_active_for_employee.return_value = []

    resolver = HumanConversationActorResolver(
        external_identity_repository=external_identity_repository,
        group_membership_repository=group_membership_repository,
    )

    actor = await resolver.resolve(
        subject=SUBJECT,
    )

    assert actor.employee_id == employee_id
    assert actor.member_group_ids == frozenset()
    assert actor.administered_group_ids == frozenset()


@pytest.mark.asyncio
async def test_empty_subject_is_rejected_before_repository_access() -> None:
    external_identity_repository = AsyncMock(
        spec=ExternalIdentityRepository,
    )

    group_membership_repository = AsyncMock(
        spec=GroupMembershipRepository,
    )

    resolver = HumanConversationActorResolver(
        external_identity_repository=external_identity_repository,
        group_membership_repository=group_membership_repository,
    )

    with pytest.raises(
        ValueError,
        match="subject must not be empty",
    ):
        await resolver.resolve(
            subject="   ",
        )

    external_identity_repository.get_active_employee_by_provider_user.assert_not_awaited()

    group_membership_repository.list_active_for_employee.assert_not_awaited()
