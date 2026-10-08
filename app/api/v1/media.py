from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.rate_limits import require_media_url_rate_limit
from app.api.dependencies.database import (
    get_db_session,
)
from app.api.dependencies.human_context import (
    HumanConversationRequestContext,
    require_human_conversation_request_context,
)
from app.core.config import get_settings
from app.integrations.s3.client import (
    ManagedS3Client,
    S3ClientConfig,
)
from app.repositories.media_access import (
    MediaAccessRepository,
)
from app.services.media_presigned_url import (
    MediaAccessDeniedError,
    MediaNotFoundError,
    MediaPresignedURLService,
    MediaStorageUnavailableError,
)


router = APIRouter(
    tags=["media"],
)


MEDIA_NOT_FOUND = "MEDIA_NOT_FOUND"
MEDIA_ACCESS_DENIED = "MEDIA_ACCESS_DENIED"
MEDIA_STORAGE_UNAVAILABLE = "MEDIA_STORAGE_UNAVAILABLE"


class MediaURLResponse(BaseModel):
    url: str
    expires_in_seconds: int
    expires_at: datetime


def _media_http_exception(
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


@router.get(
    "/messages/{message_id}/media/{media_id}/url",
    response_model=MediaURLResponse,
    dependencies=[
        Depends(require_media_url_rate_limit),
    ],
)
async def get_media_url(
    message_id: UUID,
    media_id: UUID,
    request_context: Annotated[
        HumanConversationRequestContext,
        Depends(require_human_conversation_request_context),
    ],
    session: Annotated[
        AsyncSession,
        Depends(get_db_session),
    ],
) -> MediaURLResponse:
    settings = get_settings()

    repository = MediaAccessRepository(
        session=session,
        tenant=request_context.tenant,
    )

    storage = ManagedS3Client(
        S3ClientConfig(
            region_name=settings.s3_region,
            endpoint_url=(settings.s3_public_endpoint_url or settings.s3_endpoint_url),
            access_key_id=(settings.s3_access_key_id),
            secret_access_key=(settings.s3_secret_access_key),
            session_token=(settings.s3_session_token),
            addressing_style=(settings.s3_addressing_style),
        )
    )

    service = MediaPresignedURLService(
        repository=repository,
        storage=storage,
        expiry_seconds=(settings.media_presigned_url_expiry_seconds),
    )

    try:
        result = await service.create_url(
            message_id=message_id,
            media_id=media_id,
            context=(request_context.authorization),
            actor=request_context.actor,
        )

    except MediaNotFoundError as exc:
        raise _media_http_exception(
            status_code=(status.HTTP_404_NOT_FOUND),
            code=MEDIA_NOT_FOUND,
            message="Media was not found.",
        ) from exc

    except MediaAccessDeniedError as exc:
        raise _media_http_exception(
            status_code=(status.HTTP_403_FORBIDDEN),
            code=MEDIA_ACCESS_DENIED,
            message=("Media access is not allowed."),
        ) from exc

    except MediaStorageUnavailableError as exc:
        raise _media_http_exception(
            status_code=(status.HTTP_503_SERVICE_UNAVAILABLE),
            code=(MEDIA_STORAGE_UNAVAILABLE),
            message=("Media storage is temporarily unavailable."),
        ) from exc

    return MediaURLResponse(
        url=result.url,
        expires_in_seconds=(result.expires_in_seconds),
        expires_at=result.expires_at,
    )
