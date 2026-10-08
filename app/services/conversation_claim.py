from __future__ import annotations

from uuid import UUID, uuid4

from app.authorization.context import AuthorizationContext
from app.authorization.conversation import (
    ConversationAccessResource,
    ConversationActorContext,
    can_claim_conversation,
)
from app.db.models.conversation import (
    Conversation,
    ConversationState,
)
from app.repositories.business_audit_log import (
    BusinessAuditLogRepository,
)
from app.repositories.conversation import (
    ConversationRepository,
)
from app.repositories.conversation_assignment_history import (
    ConversationAssignmentHistoryRepository,
)


class ConversationNotFoundError(Exception):
    """Raised when the conversation is not visible in the tenant scope."""


class ConversationClaimNotAllowedError(Exception):
    """Raised when the actor may not claim the conversation."""


class ConversationAlreadyClaimedError(Exception):
    """Raised when another actor wins the atomic claim race."""


class ConversationClaimService:
    def __init__(
        self,
        repository: ConversationRepository,
        assignment_history_repository: (ConversationAssignmentHistoryRepository),
        audit_repository: BusinessAuditLogRepository,
    ) -> None:
        self._repository = repository
        self._assignment_history_repository = assignment_history_repository
        self._audit_repository = audit_repository

    async def claim(
        self,
        *,
        conversation_id: UUID,
        context: AuthorizationContext,
        actor: ConversationActorContext,
    ) -> Conversation:
        tenant_id = context.tenant_id
        employee_id = actor.employee_id

        if tenant_id is None or employee_id is None:
            raise ConversationClaimNotAllowedError

        conversation = await self._repository.get_by_id(
            conversation_id,
        )

        if conversation is None:
            raise ConversationNotFoundError

        if conversation.group_id is None:
            raise ConversationClaimNotAllowedError

        resource = ConversationAccessResource(
            tenant_id=conversation.tenant_id,
            group_id=conversation.group_id,
            responsible_employee_id=(conversation.responsible_employee_id),
            is_queued=(conversation.state == ConversationState.QUEUED),
        )

        if not can_claim_conversation(
            context,
            actor,
            resource,
        ):
            raise ConversationClaimNotAllowedError

        claimed = await self._repository.atomic_claim(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            employee_id=employee_id,
        )

        if claimed is None:
            raise ConversationAlreadyClaimedError

        self._assignment_history_repository.add_claim(
            conversation_id=conversation_id,
            employee_id=employee_id,
        )

        self._audit_repository.add_conversation_claim(
            conversation_id=conversation_id,
            employee_id=employee_id,
            actor_id=context.actor_id,
            trace_id=uuid4().hex,
        )

        return claimed
