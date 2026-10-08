from __future__ import annotations

from uuid import UUID

from app.db.models.conversation_assignment_history import (
    ConversationAssignmentHistory,
    ConversationAssignmentReason,
)
from app.repositories.base import TenantScopedRepository


class ConversationAssignmentHistoryRepository(TenantScopedRepository):
    def add_claim(
        self,
        *,
        conversation_id: UUID,
        employee_id: UUID,
    ) -> ConversationAssignmentHistory:
        return self._add(
            conversation_id=conversation_id,
            previous_employee_id=None,
            new_employee_id=employee_id,
            reason=ConversationAssignmentReason.CLAIM,
        )

    def add_return_to_queue(
        self,
        *,
        conversation_id: UUID,
        previous_employee_id: UUID,
    ) -> ConversationAssignmentHistory:
        return self._add(
            conversation_id=conversation_id,
            previous_employee_id=previous_employee_id,
            new_employee_id=None,
            reason=(ConversationAssignmentReason.RETURN_TO_QUEUE),
        )

    def add_auto_reassignment(
        self,
        *,
        conversation_id: UUID,
        previous_employee_id: UUID,
        new_employee_id: UUID,
    ) -> ConversationAssignmentHistory:
        return self._add(
            conversation_id=conversation_id,
            previous_employee_id=previous_employee_id,
            new_employee_id=new_employee_id,
            reason=(ConversationAssignmentReason.AUTO_REASSIGNMENT),
        )

    def _add(
        self,
        *,
        conversation_id: UUID,
        previous_employee_id: UUID | None,
        new_employee_id: UUID | None,
        reason: ConversationAssignmentReason,
    ) -> ConversationAssignmentHistory:
        history = ConversationAssignmentHistory(
            tenant_id=self.tenant_id,
            conversation_id=conversation_id,
            previous_employee_id=previous_employee_id,
            new_employee_id=new_employee_id,
            reason=reason,
        )

        self._session.add(history)

        return history
