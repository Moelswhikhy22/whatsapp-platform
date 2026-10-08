from __future__ import annotations

from uuid import UUID

from sqlalchemy import Select, and_, func, select, update

from app.db.models.conversation import (
    Conversation,
    ConversationState,
)
from app.db.models.employee import Employee
from app.db.models.group_membership import GroupMembership
from app.repositories.base import TenantScopedRepository


class ConversationRepository(TenantScopedRepository):
    async def get_by_id(
        self,
        conversation_id: UUID,
    ) -> Conversation | None:
        statement: Select[Conversation] = self._scope(
            select(Conversation),
            Conversation.tenant_id,
        ).where(
            Conversation.id == conversation_id,
        )

        result = await self._session.scalars(statement)

        return result.first()

    async def list_shared_inbox_for_employee(
        self,
        employee_id: UUID,
    ) -> list[Conversation]:
        statement: Select[Conversation] = (
            self._scope(
                select(Conversation),
                Conversation.tenant_id,
            )
            .join(
                GroupMembership,
                and_(
                    GroupMembership.tenant_id == Conversation.tenant_id,
                    GroupMembership.group_id == Conversation.group_id,
                ),
            )
            .where(
                GroupMembership.employee_id == employee_id,
                GroupMembership.active.is_(True),
                Conversation.state == ConversationState.QUEUED,
                Conversation.responsible_employee_id.is_(None),
            )
            .order_by(
                Conversation.created_at.asc(),
                Conversation.id.asc(),
            )
        )

        result = await self._session.scalars(statement)

        return list(result.all())

    async def list_eligible_team_member_ids(
        self,
        group_id: UUID,
    ) -> list[UUID]:
        statement = (
            self._scope(
                select(Employee.id),
                Employee.tenant_id,
            )
            .join(
                GroupMembership,
                and_(
                    GroupMembership.tenant_id == Employee.tenant_id,
                    GroupMembership.employee_id == Employee.id,
                ),
            )
            .where(
                GroupMembership.group_id == group_id,
                GroupMembership.active.is_(True),
                Employee.active.is_(True),
            )
            .order_by(Employee.id.asc())
        )

        result = await self._session.scalars(statement)

        return list(result.all())

    async def atomic_claim(
        self,
        *,
        tenant_id: UUID,
        conversation_id: UUID,
        employee_id: UUID,
    ) -> Conversation | None:
        statement = (
            update(Conversation)
            .where(
                Conversation.tenant_id == tenant_id,
                Conversation.id == conversation_id,
                Conversation.state == ConversationState.QUEUED,
                Conversation.responsible_employee_id.is_(None),
            )
            .values(
                responsible_employee_id=employee_id,
                state=ConversationState.CLAIMED,
                claimed_at=func.now(),
                updated_at=func.now(),
            )
            .returning(Conversation)
        )

        result = await self._session.scalars(statement)

        return result.first()

    async def atomic_transition_state(
        self,
        *,
        conversation_id: UUID,
        expected_current_state: ConversationState,
        target_state: ConversationState,
    ) -> Conversation | None:
        statement = (
            update(Conversation)
            .where(
                Conversation.tenant_id == self.tenant_id,
                Conversation.id == conversation_id,
                Conversation.state == expected_current_state,
            )
            .values(
                state=target_state,
                updated_at=func.now(),
            )
            .returning(Conversation)
        )

        result = await self._session.scalars(statement)

        return result.first()

    async def atomic_return_to_queue(
        self,
        *,
        conversation_id: UUID,
        expected_owner_id: UUID,
        expected_current_state: ConversationState,
    ) -> Conversation | None:
        statement = (
            update(Conversation)
            .where(
                Conversation.tenant_id == self.tenant_id,
                Conversation.id == conversation_id,
                Conversation.state == expected_current_state,
                Conversation.responsible_employee_id == expected_owner_id,
            )
            .values(
                responsible_employee_id=None,
                state=ConversationState.QUEUED,
                claimed_at=None,
                updated_at=func.now(),
            )
            .returning(Conversation)
        )

        result = await self._session.scalars(statement)

        return result.first()

    async def atomic_reassign_owner(
        self,
        *,
        conversation_id: UUID,
        expected_owner_id: UUID,
        expected_current_state: ConversationState,
        new_owner_id: UUID,
    ) -> Conversation | None:
        statement = (
            update(Conversation)
            .where(
                Conversation.tenant_id == self.tenant_id,
                Conversation.id == conversation_id,
                Conversation.state == expected_current_state,
                Conversation.responsible_employee_id == expected_owner_id,
            )
            .values(
                responsible_employee_id=new_owner_id,
                updated_at=func.now(),
            )
            .returning(Conversation)
        )

        result = await self._session.scalars(statement)

        return result.first()
