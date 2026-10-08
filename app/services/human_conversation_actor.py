from __future__ import annotations

from app.authorization.conversation import ConversationActorContext
from app.repositories.external_identity import ExternalIdentityRepository
from app.repositories.group_membership import GroupMembershipRepository

KEYCLOAK_IDENTITY_PROVIDER = "keycloak"


class HumanConversationActorResolver:
    def __init__(
        self,
        *,
        external_identity_repository: ExternalIdentityRepository,
        group_membership_repository: GroupMembershipRepository,
    ) -> None:
        self._external_identity_repository = external_identity_repository
        self._group_membership_repository = group_membership_repository

    async def resolve(
        self,
        *,
        subject: str,
    ) -> ConversationActorContext:
        if not subject.strip():
            raise ValueError("subject must not be empty")

        employee = await self._external_identity_repository.get_active_employee_by_provider_user(
            provider=KEYCLOAK_IDENTITY_PROVIDER,
            external_user_id=subject,
        )

        if employee is None:
            return ConversationActorContext()

        memberships = await self._group_membership_repository.list_active_for_employee(
            employee.id,
        )

        member_group_ids = frozenset(membership.group_id for membership in memberships)

        administered_group_ids = frozenset(
            membership.group_id for membership in memberships if membership.is_admin
        )

        return ConversationActorContext(
            employee_id=employee.id,
            member_group_ids=member_group_ids,
            administered_group_ids=administered_group_ids,
        )
