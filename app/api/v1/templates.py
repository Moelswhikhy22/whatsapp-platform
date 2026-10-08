from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    status,
)
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.database import (
    get_db_session,
)
from app.api.dependencies.human_context import (
    HumanConversationRequestContext,
    require_human_conversation_request_context,
)
from app.db.models.security_access_log import (
    SecurityAccessOutcome,
    SecurityPrincipalType,
)
from app.db.models.template import (
    Template,
    TemplateType,
)
from app.repositories.template import (
    TemplateRepository,
)
from app.security_access import (
    record_security_access,
)
from app.services.internal_template import (
    InternalTemplateInvalidUpdateError,
    InternalTemplateNameConflictError,
    InternalTemplateNotAllowedError,
    InternalTemplateNotFoundError,
    InternalTemplateService,
)


router = APIRouter(
    prefix="/templates",
    tags=["templates"],
)

TEMPLATE_NOT_FOUND = "TEMPLATE_NOT_FOUND"
TEMPLATE_ACTION_NOT_ALLOWED = "TEMPLATE_ACTION_NOT_ALLOWED"
TEMPLATE_NAME_CONFLICT = "TEMPLATE_NAME_CONFLICT"
TEMPLATE_INVALID_UPDATE = "TEMPLATE_INVALID_UPDATE"


class InternalTemplateCreateRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    template_type: Literal["internal"] = "internal"

    name: str = Field(
        min_length=1,
        max_length=255,
    )

    category: str = Field(
        min_length=1,
        max_length=100,
    )

    body: str = Field(
        min_length=1,
    )

    variables: list[object] = Field(
        default_factory=list,
    )

    @field_validator(
        "name",
        "category",
    )
    @classmethod
    def normalize_short_text(
        cls,
        value: str,
    ) -> str:
        normalized = value.strip()

        if not normalized:
            raise ValueError("Value must not be blank.")

        return normalized

    @field_validator("body")
    @classmethod
    def validate_body(
        cls,
        value: str,
    ) -> str:
        if not value.strip():
            raise ValueError("Template body must not be blank.")

        return value


class InternalTemplatePatchRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
    )

    category: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )

    body: str | None = Field(
        default=None,
        min_length=1,
    )

    variables: list[object] | None = None

    active: bool | None = None

    @model_validator(mode="before")
    @classmethod
    def reject_empty_or_null_patch(
        cls,
        value: object,
    ) -> object:
        if not isinstance(value, dict):
            return value

        if not value:
            raise ValueError("At least one template field is required.")

        for key, item in value.items():
            if item is None:
                raise ValueError(f"{key} cannot be null.")

        return value

    @field_validator(
        "name",
        "category",
    )
    @classmethod
    def normalize_short_text(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        normalized = value.strip()

        if not normalized:
            raise ValueError("Value must not be blank.")

        return normalized

    @field_validator("body")
    @classmethod
    def validate_body(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        if not value.strip():
            raise ValueError("Template body must not be blank.")

        return value


class InternalTemplateResponse(BaseModel):
    id: UUID
    template_type: TemplateType
    name: str
    category: str
    body: str
    variables: list[object]
    active: bool


def _template_response(
    template: Template,
) -> InternalTemplateResponse:
    if (
        template.template_type is not TemplateType.INTERNAL
        or template.name is None
        or template.body is None
        or template.variables_json is None
        or template.active is None
    ):
        raise RuntimeError("Internal template has an invalid persisted shape.")

    return InternalTemplateResponse(
        id=template.id,
        template_type=template.template_type,
        name=template.name,
        category=template.category,
        body=template.body,
        variables=list(template.variables_json),
        active=template.active,
    )


def _template_http_exception(
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
) -> InternalTemplateService:
    repository = TemplateRepository(
        session=session,
        tenant_id=request_context.tenant.tenant_id,
    )

    return InternalTemplateService(repository)


@router.get(
    "",
    response_model=list[InternalTemplateResponse],
)
async def list_templates(
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
    template_type: Annotated[
        Literal["internal"],
        Query(),
    ] = "internal",
    active: Annotated[
        bool | None,
        Query(),
    ] = None,
) -> list[InternalTemplateResponse]:
    del template_type

    service = _build_service(
        session=session,
        request_context=request_context,
    )

    try:
        templates = await service.list_internal(
            context=request_context.authorization,
            active=active,
        )
    except InternalTemplateNotAllowedError as exc:
        raise _template_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code=TEMPLATE_ACTION_NOT_ALLOWED,
            message="Template access is not allowed for this actor.",
        ) from exc

    return [_template_response(template) for template in templates]


@router.get(
    "/{template_id}",
    response_model=InternalTemplateResponse,
)
async def get_template(
    template_id: UUID,
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
) -> InternalTemplateResponse:
    service = _build_service(
        session=session,
        request_context=request_context,
    )

    try:
        template = await service.get_internal(
            template_id=template_id,
            context=request_context.authorization,
        )
    except InternalTemplateNotFoundError as exc:
        raise _template_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code=TEMPLATE_NOT_FOUND,
            message="Template was not found.",
        ) from exc
    except InternalTemplateNotAllowedError as exc:
        raise _template_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code=TEMPLATE_ACTION_NOT_ALLOWED,
            message="Template access is not allowed for this actor.",
        ) from exc

    return _template_response(template)


@router.post(
    "",
    response_model=InternalTemplateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_template(
    payload: InternalTemplateCreateRequest,
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
) -> InternalTemplateResponse:
    service = _build_service(
        session=session,
        request_context=request_context,
    )

    try:
        template = await service.create_internal(
            context=request_context.authorization,
            name=payload.name,
            category=payload.category,
            body=payload.body,
            variables=payload.variables,
        )

        await session.commit()

    except InternalTemplateNotAllowedError as exc:
        await session.rollback()

        await record_security_access(
            request=request,
            principal_type=SecurityPrincipalType.HUMAN,
            principal_id=request_context.principal.subject,
            tenant_id=request_context.tenant.tenant_id,
            event="authorization.denied",
            outcome=SecurityAccessOutcome.DENIED,
            resource_type="template",
            resource_id=None,
            reason_code="template_create_not_allowed",
        )

        raise _template_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code=TEMPLATE_ACTION_NOT_ALLOWED,
            message="Template creation is not allowed for this actor.",
        ) from exc

    except InternalTemplateNameConflictError as exc:
        await session.rollback()

        raise _template_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            code=TEMPLATE_NAME_CONFLICT,
            message="An internal template with this name already exists.",
        ) from exc

    except IntegrityError as exc:
        await session.rollback()

        raise _template_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            code=TEMPLATE_NAME_CONFLICT,
            message="An internal template with this name already exists.",
        ) from exc

    return _template_response(template)


@router.patch(
    "/{template_id}",
    response_model=InternalTemplateResponse,
)
async def update_template(
    template_id: UUID,
    payload: InternalTemplatePatchRequest,
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
) -> InternalTemplateResponse:
    service = _build_service(
        session=session,
        request_context=request_context,
    )

    changes = payload.model_dump(
        exclude_unset=True,
    )

    try:
        template = await service.update_internal(
            template_id=template_id,
            context=request_context.authorization,
            changes=changes,
        )

        await session.commit()

    except InternalTemplateNotFoundError as exc:
        await session.rollback()

        raise _template_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code=TEMPLATE_NOT_FOUND,
            message="Template was not found.",
        ) from exc

    except InternalTemplateNotAllowedError as exc:
        await session.rollback()

        await record_security_access(
            request=request,
            principal_type=SecurityPrincipalType.HUMAN,
            principal_id=request_context.principal.subject,
            tenant_id=request_context.tenant.tenant_id,
            event="authorization.denied",
            outcome=SecurityAccessOutcome.DENIED,
            resource_type="template",
            resource_id=str(template_id),
            reason_code="template_update_not_allowed",
        )

        raise _template_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code=TEMPLATE_ACTION_NOT_ALLOWED,
            message="Template update is not allowed for this actor.",
        ) from exc

    except InternalTemplateNameConflictError as exc:
        await session.rollback()

        raise _template_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            code=TEMPLATE_NAME_CONFLICT,
            message="An internal template with this name already exists.",
        ) from exc

    except InternalTemplateInvalidUpdateError as exc:
        await session.rollback()

        raise _template_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code=TEMPLATE_INVALID_UPDATE,
            message="Template update is invalid.",
        ) from exc

    except IntegrityError as exc:
        await session.rollback()

        raise _template_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            code=TEMPLATE_NAME_CONFLICT,
            message="An internal template with this name already exists.",
        ) from exc

    return _template_response(template)
