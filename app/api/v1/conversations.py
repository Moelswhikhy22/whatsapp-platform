from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    status,
)
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.database import get_db_session
from app.api.dependencies.human_context import (
    HumanConversationRequestContext,
    require_human_conversation_request_context,
)
from app.db.models.conversation import ConversationState
from app.repositories.business_audit_log import (
    BusinessAuditLogRepository,
)
from app.repositories.conversation import (
    ConversationRepository,
)
from app.repositories.conversation_assignment_history import (
    ConversationAssignmentHistoryRepository,
)
from app.db.models.security_access_log import (
    SecurityAccessOutcome,
    SecurityPrincipalType,
)
from app.security_access import (
    record_security_access,
)
from app.services.conversation_claim import (
    ConversationAlreadyClaimedError,
    ConversationClaimNotAllowedError,
    ConversationClaimService,
    ConversationNotFoundError,
)

router = APIRouter(
    prefix="/conversations",
    tags=["conversations"],
)

CONVERSATION_NOT_FOUND = "CONVERSATION_NOT_FOUND"
CONVERSATION_CLAIM_NOT_ALLOWED = "CONVERSATION_CLAIM_NOT_ALLOWED"
CONVERSATION_ALREADY_CLAIMED = "CONVERSATION_ALREADY_CLAIMED"


class ConversationClaimResponse(BaseModel):
    id: UUID
    state: ConversationState
    responsible_employee_id: UUID
    claimed_at: datetime | None


def _claim_http_exception(
    *,
    status_code: int,
    code: str,
    message: str,
) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={
            "code": code,
            "message": message,
        },
    )


@router.post(
    "/{conversation_id}/claim",
    response_model=ConversationClaimResponse,
    status_code=status.HTTP_200_OK,
)
async def claim_conversation(
    conversation_id: UUID,
    request: Request,
    request_context: Annotated[
        HumanConversationRequestContext,
        Depends(
            require_human_conversation_request_context,
        ),
    ],
    session: Annotated[
        AsyncSession,
        Depends(get_db_session),
    ],
) -> ConversationClaimResponse:
    repository = ConversationRepository(
        session=session,
        tenant=request_context.tenant,
    )

    assignment_history_repository = ConversationAssignmentHistoryRepository(
        session=session,
        tenant=request_context.tenant,
    )

    audit_repository = BusinessAuditLogRepository(
        session=session,
        tenant=request_context.tenant,
    )

    service = ConversationClaimService(
        repository,
        assignment_history_repository,
        audit_repository,
    )

    try:
        claimed = await service.claim(
            conversation_id=conversation_id,
            context=request_context.authorization,
            actor=request_context.actor,
        )
    except ConversationNotFoundError as exc:
        await session.rollback()

        raise _claim_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code=CONVERSATION_NOT_FOUND,
            message="Conversation was not found.",
        ) from exc
    except ConversationClaimNotAllowedError as exc:
        await session.rollback()

        await record_security_access(
            request=request,
            principal_type=(SecurityPrincipalType.HUMAN),
            principal_id=(request_context.principal.subject),
            tenant_id=(request_context.tenant.tenant_id),
            event="authorization.denied",
            outcome=(SecurityAccessOutcome.DENIED),
            resource_type="conversation",
            resource_id=str(conversation_id),
            reason_code=("conversation_claim_not_allowed"),
        )

        raise _claim_http_exception(
            status_code=(status.HTTP_403_FORBIDDEN),
            code=CONVERSATION_CLAIM_NOT_ALLOWED,
            message=("Conversation cannot be claimed by this actor."),
        ) from exc

    except ConversationAlreadyClaimedError as exc:
        await session.rollback()

        raise _claim_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            code=CONVERSATION_ALREADY_CLAIMED,
            message="Conversation has already been claimed.",
        ) from exc

    await session.commit()

    responsible_employee_id = claimed.responsible_employee_id

    if responsible_employee_id is None:
        raise RuntimeError(
            "Claimed conversation has no responsible employee.",
        )

    return ConversationClaimResponse(
        id=claimed.id,
        state=claimed.state,
        responsible_employee_id=(responsible_employee_id),
        claimed_at=claimed.claimed_at,
    )
