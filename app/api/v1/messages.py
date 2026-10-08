from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Request,
    status,
)
from pydantic import (
    BaseModel,
    Field,
    field_validator,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.database import (
    get_db_session,
)
from app.api.rate_limits import (
    require_message_send_rate_limit,
)
from app.api.dependencies.human_context import (
    HumanConversationRequestContext,
    require_human_conversation_request_context,
)
from app.db.models.message import (
    MessageStatus,
)
from app.db.models.security_access_log import (
    SecurityAccessOutcome,
    SecurityPrincipalType,
)
from app.repositories.outbound_message import (
    OutboundMessageRepository,
)
from app.repositories.outbox_event import (
    OutboxEventRepository,
)
from app.security_access import (
    record_security_access,
)
from app.services.outbound_message import (
    IdempotencyKeyConflictError,
    IdempotencyStateError,
    InvalidIdempotencyKeyError,
    MetaMessagingWindowClosedError,
    OutboundChannelUnavailableError,
    OutboundConversationNotFoundError,
    OutboundMessageNotAllowedError,
    OutboundMessageService,
    OutboundTemplateAccountMismatchError,
    OutboundTemplateNotAllowedError,
    OutboundTemplateNotApprovedError,
    OutboundTemplateNotFoundError,
    OutboundTemplatePayloadInvalidError,
)


router = APIRouter(
    tags=["messages"],
)


CONVERSATION_NOT_FOUND = "CONVERSATION_NOT_FOUND"

MESSAGE_SEND_NOT_ALLOWED = "MESSAGE_SEND_NOT_ALLOWED"

META_MESSAGING_WINDOW_CLOSED = "META_MESSAGING_WINDOW_CLOSED"

INVALID_IDEMPOTENCY_KEY = "INVALID_IDEMPOTENCY_KEY"

IDEMPOTENCY_KEY_REUSED = "IDEMPOTENCY_KEY_REUSED"

META_TEMPLATE_NOT_FOUND = "META_TEMPLATE_NOT_FOUND"

TEMPLATE_SEND_NOT_ALLOWED = "TEMPLATE_SEND_NOT_ALLOWED"

META_TEMPLATE_NOT_APPROVED = "META_TEMPLATE_NOT_APPROVED"

META_TEMPLATE_ACCOUNT_MISMATCH = "META_TEMPLATE_ACCOUNT_MISMATCH"

META_TEMPLATE_PAYLOAD_INVALID = "META_TEMPLATE_PAYLOAD_INVALID"

OUTBOUND_CHANNEL_UNAVAILABLE = "OUTBOUND_CHANNEL_UNAVAILABLE"


class TextMessageRequest(BaseModel):
    body: str = Field(
        min_length=1,
    )


class TemplateMessageRequest(BaseModel):
    template_id: UUID

    components: list[dict[str, object]] = Field(
        default_factory=list,
    )

    @field_validator("components")
    @classmethod
    def validate_components(
        cls,
        value: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        for component in value:
            raw_type = component.get("type")

            if (
                not isinstance(
                    raw_type,
                    str,
                )
                or not raw_type.strip()
            ):
                raise ValueError("Each component must contain a non-empty type.")

        return value


class MessageAcceptedResponse(BaseModel):
    id: UUID
    conversation_id: UUID
    status: MessageStatus
    idempotent_replay: bool


def _message_http_exception(
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


def _build_service(
    *,
    session: AsyncSession,
    request_context: HumanConversationRequestContext,
) -> OutboundMessageService:
    repository = OutboundMessageRepository(
        session=session,
        tenant=request_context.tenant,
    )

    outbox_repository = OutboxEventRepository(
        session=session,
        tenant=request_context.tenant,
    )

    return OutboundMessageService(
        repository=repository,
        outbox_repository=outbox_repository,
    )


def _accepted_response(
    result_message,
    *,
    idempotent_replay: bool,
) -> MessageAcceptedResponse:
    message_status = result_message.status

    if message_status is None:
        raise RuntimeError("Accepted outbound message has no status.")

    return MessageAcceptedResponse(
        id=result_message.id,
        conversation_id=result_message.conversation_id,
        status=message_status,
        idempotent_replay=idempotent_replay,
    )


@router.post(
    "/conversations/{conversation_id}/messages/text",
    response_model=MessageAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[
        Depends(require_message_send_rate_limit),
    ],
)
async def send_text_message(
    conversation_id: UUID,
    payload: TextMessageRequest,
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
    idempotency_key: Annotated[
        str | None,
        Header(alias="Idempotency-Key"),
    ] = None,
) -> MessageAcceptedResponse:
    service = _build_service(
        session=session,
        request_context=request_context,
    )

    try:
        result = await service.send_text(
            conversation_id=conversation_id,
            body_text=payload.body,
            context=request_context.authorization,
            actor=request_context.actor,
            idempotency_key=idempotency_key,
        )

    except OutboundConversationNotFoundError as exc:
        await session.rollback()

        raise _message_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code=CONVERSATION_NOT_FOUND,
            message="Conversation was not found.",
        ) from exc

    except OutboundMessageNotAllowedError as exc:
        await session.rollback()

        await record_security_access(
            request=request,
            principal_type=SecurityPrincipalType.HUMAN,
            principal_id=request_context.principal.subject,
            tenant_id=request_context.tenant.tenant_id,
            event="authorization.denied",
            outcome=SecurityAccessOutcome.DENIED,
            resource_type="conversation",
            resource_id=str(conversation_id),
            reason_code="message_send_not_allowed",
        )

        raise _message_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code=MESSAGE_SEND_NOT_ALLOWED,
            message=("Message sending is not allowed for this conversation."),
        ) from exc

    except MetaMessagingWindowClosedError as exc:
        await session.rollback()

        raise _message_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            code=META_MESSAGING_WINDOW_CLOSED,
            message=(
                "Free-text messaging is "
                "outside the customer-service "
                "window; an eligible template "
                "is required."
            ),
        ) from exc

    except InvalidIdempotencyKeyError as exc:
        await session.rollback()

        raise _message_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code=INVALID_IDEMPOTENCY_KEY,
            message=str(exc),
        ) from exc

    except IdempotencyKeyConflictError as exc:
        await session.rollback()

        raise _message_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            code=IDEMPOTENCY_KEY_REUSED,
            message=("Idempotency-Key was already used for a different request."),
        ) from exc

    except IdempotencyStateError:
        await session.rollback()
        raise

    await session.commit()

    return _accepted_response(
        result.message,
        idempotent_replay=result.idempotent_replay,
    )


@router.post(
    "/conversations/{conversation_id}/messages/template",
    response_model=MessageAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[
        Depends(require_message_send_rate_limit),
    ],
)
async def send_template_message(
    conversation_id: UUID,
    payload: TemplateMessageRequest,
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
    idempotency_key: Annotated[
        str | None,
        Header(alias="Idempotency-Key"),
    ] = None,
) -> MessageAcceptedResponse:
    service = _build_service(
        session=session,
        request_context=request_context,
    )

    try:
        result = await service.send_template(
            conversation_id=conversation_id,
            template_id=payload.template_id,
            components=payload.components,
            context=request_context.authorization,
            actor=request_context.actor,
            idempotency_key=idempotency_key,
        )

    except OutboundConversationNotFoundError as exc:
        await session.rollback()

        raise _message_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code=CONVERSATION_NOT_FOUND,
            message="Conversation was not found.",
        ) from exc

    except OutboundMessageNotAllowedError as exc:
        await session.rollback()

        await record_security_access(
            request=request,
            principal_type=SecurityPrincipalType.HUMAN,
            principal_id=request_context.principal.subject,
            tenant_id=request_context.tenant.tenant_id,
            event="authorization.denied",
            outcome=SecurityAccessOutcome.DENIED,
            resource_type="conversation",
            resource_id=str(conversation_id),
            reason_code="message_send_not_allowed",
        )

        raise _message_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code=MESSAGE_SEND_NOT_ALLOWED,
            message=("Message sending is not allowed for this conversation."),
        ) from exc

    except OutboundTemplateNotFoundError as exc:
        await session.rollback()

        raise _message_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code=META_TEMPLATE_NOT_FOUND,
            message="Meta template was not found.",
        ) from exc

    except OutboundTemplateNotAllowedError as exc:
        await session.rollback()

        await record_security_access(
            request=request,
            principal_type=SecurityPrincipalType.HUMAN,
            principal_id=request_context.principal.subject,
            tenant_id=request_context.tenant.tenant_id,
            event="authorization.denied",
            outcome=SecurityAccessOutcome.DENIED,
            resource_type="template",
            resource_id=str(payload.template_id),
            reason_code="template_send_not_allowed",
        )

        raise _message_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code=TEMPLATE_SEND_NOT_ALLOWED,
            message="Template sending is not allowed for this actor.",
        ) from exc

    except OutboundTemplateNotApprovedError as exc:
        await session.rollback()

        raise _message_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            code=META_TEMPLATE_NOT_APPROVED,
            message="Only approved Meta templates can be sent.",
        ) from exc

    except OutboundTemplateAccountMismatchError as exc:
        await session.rollback()

        raise _message_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            code=META_TEMPLATE_ACCOUNT_MISMATCH,
            message=("The Meta template belongs to a different WhatsApp integration."),
        ) from exc

    except OutboundTemplatePayloadInvalidError as exc:
        await session.rollback()

        raise _message_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code=META_TEMPLATE_PAYLOAD_INVALID,
            message=str(exc),
        ) from exc

    except OutboundChannelUnavailableError as exc:
        await session.rollback()

        raise _message_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            code=OUTBOUND_CHANNEL_UNAVAILABLE,
            message=("The conversation WhatsApp channel is unavailable."),
        ) from exc

    except InvalidIdempotencyKeyError as exc:
        await session.rollback()

        raise _message_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code=INVALID_IDEMPOTENCY_KEY,
            message=str(exc),
        ) from exc

    except IdempotencyKeyConflictError as exc:
        await session.rollback()

        raise _message_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            code=IDEMPOTENCY_KEY_REUSED,
            message=("Idempotency-Key was already used for a different request."),
        ) from exc

    except IdempotencyStateError:
        await session.rollback()
        raise

    await session.commit()

    return _accepted_response(
        result.message,
        idempotent_replay=result.idempotent_replay,
    )
