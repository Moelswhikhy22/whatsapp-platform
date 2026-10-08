from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from app.api.dependencies.database import (
    get_db_session,
)
from app.api.dependencies.human_context import (
    HumanConversationRequestContext,
    require_human_conversation_request_context,
)
from app.authorization import (
    AuthorizationDeniedError,
    TenantIsolationError,
)
from app.db.models.conversation import (
    ConversationState,
)
from app.repositories.conversation_search import (
    ConversationSearchFilters,
    ConversationSearchRepository,
)
from app.services.conversation_search import (
    ConversationSearchService,
)


router = APIRouter(
    prefix="/conversations",
    tags=["conversations"],
)


class ConversationSearchItemResponse(BaseModel):
    id: UUID
    state: ConversationState

    customer_contact_id: UUID
    customer_name: str | None

    customer_company_id: UUID
    company_name: str

    phone_number: str

    whatsapp_number_id: UUID
    whatsapp_number: str

    group_id: UUID | None
    group_name: str | None

    responsible_employee_id: UUID | None

    created_at: datetime
    updated_at: datetime


class ConversationSearchResponse(BaseModel):
    items: list[ConversationSearchItemResponse]

    limit: int
    offset: int

    returned_count: int


@router.get(
    "",
    response_model=(ConversationSearchResponse),
)
async def search_conversations(
    request_context: Annotated[
        HumanConversationRequestContext,
        Depends(require_human_conversation_request_context),
    ],
    session: Annotated[
        AsyncSession,
        Depends(get_db_session),
    ],
    search: Annotated[
        str | None,
        Query(
            min_length=1,
            max_length=255,
        ),
    ] = None,
    conversation_id: UUID | None = None,
    customer: Annotated[
        str | None,
        Query(
            min_length=1,
            max_length=255,
        ),
    ] = None,
    company: Annotated[
        str | None,
        Query(
            min_length=1,
            max_length=255,
        ),
    ] = None,
    phone: Annotated[
        str | None,
        Query(
            min_length=1,
            max_length=64,
        ),
    ] = None,
    whatsapp_number: Annotated[
        str | None,
        Query(
            min_length=1,
            max_length=255,
        ),
    ] = None,
    responsible_employee_id: UUID | None = None,
    group_id: UUID | None = None,
    state: ConversationState | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    message_text: Annotated[
        str | None,
        Query(
            min_length=1,
            max_length=500,
        ),
    ] = None,
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=200,
        ),
    ] = 50,
    offset: Annotated[
        int,
        Query(ge=0),
    ] = 0,
) -> ConversationSearchResponse:
    if created_from is not None and created_to is not None and created_from > created_to:
        raise HTTPException(
            status_code=(status.HTTP_422_UNPROCESSABLE_CONTENT),
            detail={
                "code": ("INVALID_DATE_RANGE"),
                "message": ("created_from must be before created_to."),
            },
        )

    repository = ConversationSearchRepository(
        session=session,
        tenant=request_context.tenant,
    )

    service = ConversationSearchService(repository)

    try:
        results = await service.search(
            context=(request_context.authorization),
            actor=request_context.actor,
            filters=(
                ConversationSearchFilters(
                    search=search,
                    conversation_id=(conversation_id),
                    customer=customer,
                    company=company,
                    phone=phone,
                    whatsapp_number=(whatsapp_number),
                    responsible_employee_id=(responsible_employee_id),
                    group_id=group_id,
                    state=state,
                    created_from=(created_from),
                    created_to=created_to,
                    message_text=(message_text),
                )
            ),
            limit=limit,
            offset=offset,
        )

    except (
        AuthorizationDeniedError,
        TenantIsolationError,
    ) as exc:
        raise HTTPException(
            status_code=(status.HTTP_403_FORBIDDEN),
            detail={
                "code": ("CONVERSATION_SEARCH_FORBIDDEN"),
                "message": ("Conversation search is not allowed."),
            },
        ) from exc

    items = [
        ConversationSearchItemResponse(
            id=item.id,
            state=item.state,
            customer_contact_id=(item.customer_contact_id),
            customer_name=(item.customer_name),
            customer_company_id=(item.customer_company_id),
            company_name=(item.company_name),
            phone_number=(item.phone_number),
            whatsapp_number_id=(item.whatsapp_number_id),
            whatsapp_number=(item.whatsapp_number),
            group_id=item.group_id,
            group_name=item.group_name,
            responsible_employee_id=(item.responsible_employee_id),
            created_at=item.created_at,
            updated_at=item.updated_at,
        )
        for item in results
    ]

    return ConversationSearchResponse(
        items=items,
        limit=limit,
        offset=offset,
        returned_count=len(items),
    )
