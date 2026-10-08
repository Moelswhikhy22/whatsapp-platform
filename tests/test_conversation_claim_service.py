from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.authorization.context import AuthorizationContext
from app.authorization.conversation import (
    ConversationActorContext,
)
from app.authorization.roles import Role
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
from app.services.conversation_claim import (
    ConversationAlreadyClaimedError,
    ConversationClaimNotAllowedError,
    ConversationClaimService,
    ConversationNotFoundError,
)


def _service(
    repository: AsyncMock,
) -> tuple[
    ConversationClaimService,
    MagicMock,
    MagicMock,
]:
    assignment_history_repository = MagicMock(
        spec=ConversationAssignmentHistoryRepository,
    )

    audit_repository = MagicMock(
        spec=BusinessAuditLogRepository,
    )

    service = ConversationClaimService(
        repository,
        assignment_history_repository,
        audit_repository,
    )

    return (
        service,
        assignment_history_repository,
        audit_repository,
    )


@pytest.mark.asyncio
async def test_employee_can_claim_queued_group_conversation() -> None:
    tenant_id = uuid4()
    group_id = uuid4()
    employee_id = uuid4()
    conversation_id = uuid4()

    repository = AsyncMock(
        spec=ConversationRepository,
    )

    queued = Conversation(
        id=conversation_id,
        tenant_id=tenant_id,
        whatsapp_number_id=uuid4(),
        customer_contact_id=uuid4(),
        group_id=group_id,
        state=ConversationState.QUEUED,
        responsible_employee_id=None,
    )

    claimed = Conversation(
        id=conversation_id,
        tenant_id=tenant_id,
        whatsapp_number_id=queued.whatsapp_number_id,
        customer_contact_id=queued.customer_contact_id,
        group_id=group_id,
        state=ConversationState.CLAIMED,
        responsible_employee_id=employee_id,
    )

    repository.get_by_id.return_value = queued
    repository.atomic_claim.return_value = claimed

    (
        service,
        assignment_history_repository,
        audit_repository,
    ) = _service(repository)

    context = AuthorizationContext(
        actor_id="employee-user",
        role=Role.EMPLOYEE,
        tenant_id=tenant_id,
    )

    actor = ConversationActorContext(
        employee_id=employee_id,
        member_group_ids=frozenset(
            {
                group_id,
            }
        ),
    )

    result = await service.claim(
        conversation_id=conversation_id,
        context=context,
        actor=actor,
    )

    assert result is claimed

    repository.atomic_claim.assert_awaited_once_with(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        employee_id=employee_id,
    )

    assignment_history_repository.add_claim.assert_called_once_with(
        conversation_id=conversation_id,
        employee_id=employee_id,
    )

    audit_repository.add_conversation_claim.assert_called_once()

    audit_call = audit_repository.add_conversation_claim.call_args

    assert audit_call.kwargs["conversation_id"] == conversation_id
    assert audit_call.kwargs["employee_id"] == employee_id
    assert audit_call.kwargs["actor_id"] == "employee-user"

    trace_id = audit_call.kwargs["trace_id"]

    assert isinstance(trace_id, str)
    assert len(trace_id) == 32


@pytest.mark.asyncio
async def test_losing_atomic_claim_raises_conflict() -> None:
    tenant_id = uuid4()
    group_id = uuid4()
    employee_id = uuid4()
    conversation_id = uuid4()

    repository = AsyncMock(
        spec=ConversationRepository,
    )

    repository.get_by_id.return_value = Conversation(
        id=conversation_id,
        tenant_id=tenant_id,
        whatsapp_number_id=uuid4(),
        customer_contact_id=uuid4(),
        group_id=group_id,
        state=ConversationState.QUEUED,
        responsible_employee_id=None,
    )

    repository.atomic_claim.return_value = None

    (
        service,
        assignment_history_repository,
        audit_repository,
    ) = _service(repository)

    context = AuthorizationContext(
        actor_id="employee-user",
        role=Role.EMPLOYEE,
        tenant_id=tenant_id,
    )

    actor = ConversationActorContext(
        employee_id=employee_id,
        member_group_ids=frozenset(
            {
                group_id,
            }
        ),
    )

    with pytest.raises(
        ConversationAlreadyClaimedError,
    ):
        await service.claim(
            conversation_id=conversation_id,
            context=context,
            actor=actor,
        )

    assignment_history_repository.add_claim.assert_not_called()
    audit_repository.add_conversation_claim.assert_not_called()


@pytest.mark.asyncio
async def test_claim_rejects_unknown_conversation() -> None:
    repository = AsyncMock(
        spec=ConversationRepository,
    )
    repository.get_by_id.return_value = None

    (
        service,
        assignment_history_repository,
        audit_repository,
    ) = _service(repository)

    with pytest.raises(
        ConversationNotFoundError,
    ):
        await service.claim(
            conversation_id=uuid4(),
            context=AuthorizationContext(
                actor_id="employee-user",
                role=Role.EMPLOYEE,
                tenant_id=uuid4(),
            ),
            actor=ConversationActorContext(
                employee_id=uuid4(),
            ),
        )

    repository.atomic_claim.assert_not_awaited()
    assignment_history_repository.add_claim.assert_not_called()
    audit_repository.add_conversation_claim.assert_not_called()


@pytest.mark.asyncio
async def test_employee_cannot_claim_other_group_conversation() -> None:
    tenant_id = uuid4()
    conversation_group_id = uuid4()
    employee_group_id = uuid4()

    repository = AsyncMock(
        spec=ConversationRepository,
    )

    repository.get_by_id.return_value = Conversation(
        id=uuid4(),
        tenant_id=tenant_id,
        whatsapp_number_id=uuid4(),
        customer_contact_id=uuid4(),
        group_id=conversation_group_id,
        state=ConversationState.QUEUED,
        responsible_employee_id=None,
    )

    (
        service,
        assignment_history_repository,
        audit_repository,
    ) = _service(repository)

    with pytest.raises(
        ConversationClaimNotAllowedError,
    ):
        await service.claim(
            conversation_id=uuid4(),
            context=AuthorizationContext(
                actor_id="employee-user",
                role=Role.EMPLOYEE,
                tenant_id=tenant_id,
            ),
            actor=ConversationActorContext(
                employee_id=uuid4(),
                member_group_ids=frozenset(
                    {
                        employee_group_id,
                    }
                ),
            ),
        )

    repository.atomic_claim.assert_not_awaited()
    assignment_history_repository.add_claim.assert_not_called()
    audit_repository.add_conversation_claim.assert_not_called()
