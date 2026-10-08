from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.database import (
    get_db_session,
)
from app.api.dependencies.meta_webhook import (
    get_meta_webhook_credential_provider,
)
from app.integrations.meta.webhook_security import (
    MetaWebhookCredentialProvider,
    MetaWebhookCredentialsUnavailableError,
)
from app.repositories.meta_webhook import (
    MetaWebhookRepository,
)
from app.services.meta_webhook import (
    MetaWebhookIngressService,
    MetaWebhookIntegrationNotFoundError,
    MetaWebhookInvalidPayloadError,
    MetaWebhookInvalidSignatureError,
    MetaWebhookVerificationError,
)

router = APIRouter(
    prefix="/webhooks/meta",
    tags=["Meta Webhooks"],
)


@router.get(
    "/{integration_id}",
    response_class=PlainTextResponse,
)
async def verify_meta_webhook(
    integration_id: UUID,
    session: Annotated[
        AsyncSession,
        Depends(get_db_session),
    ],
    credential_provider: Annotated[
        MetaWebhookCredentialProvider,
        Depends(get_meta_webhook_credential_provider),
    ],
    hub_mode: Annotated[
        str,
        Query(alias="hub.mode"),
    ],
    hub_verify_token: Annotated[
        str,
        Query(alias="hub.verify_token"),
    ],
    hub_challenge: Annotated[
        str,
        Query(alias="hub.challenge"),
    ],
) -> PlainTextResponse:
    repository = MetaWebhookRepository(session)

    service = MetaWebhookIngressService(
        repository=repository,
        credential_provider=(credential_provider),
    )

    try:
        challenge = await service.verify_challenge(
            integration_id=integration_id,
            mode=hub_mode,
            verify_token=(hub_verify_token),
            challenge=hub_challenge,
        )
    except MetaWebhookIntegrationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=("Meta integration was not found."),
        ) from exc
    except MetaWebhookVerificationError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=("Meta webhook verification failed."),
        ) from exc
    except MetaWebhookCredentialsUnavailableError as exc:
        raise HTTPException(
            status_code=(status.HTTP_503_SERVICE_UNAVAILABLE),
            detail=("Meta webhook credentials are unavailable."),
        ) from exc

    return PlainTextResponse(
        challenge,
        status_code=status.HTTP_200_OK,
    )


@router.post(
    "/{integration_id}",
    status_code=status.HTTP_200_OK,
)
async def receive_meta_webhook(
    integration_id: UUID,
    request: Request,
    session: Annotated[
        AsyncSession,
        Depends(get_db_session),
    ],
    credential_provider: Annotated[
        MetaWebhookCredentialProvider,
        Depends(get_meta_webhook_credential_provider),
    ],
) -> Response:
    raw_body = await request.body()

    signature_header = request.headers.get("X-Hub-Signature-256")

    repository = MetaWebhookRepository(session)

    service = MetaWebhookIngressService(
        repository=repository,
        credential_provider=(credential_provider),
    )

    try:
        await service.receive(
            integration_id=integration_id,
            raw_body=raw_body,
            signature_header=(signature_header),
        )

        await session.commit()

    except MetaWebhookIntegrationNotFoundError as exc:
        await session.rollback()

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=("Meta integration was not found."),
        ) from exc

    except MetaWebhookInvalidSignatureError as exc:
        await session.rollback()

        raise HTTPException(
            status_code=(status.HTTP_401_UNAUTHORIZED),
            detail=("Invalid Meta webhook signature."),
        ) from exc

    except MetaWebhookInvalidPayloadError as exc:
        await session.rollback()

        raise HTTPException(
            status_code=(status.HTTP_400_BAD_REQUEST),
            detail=("Invalid Meta webhook payload."),
        ) from exc

    except MetaWebhookCredentialsUnavailableError as exc:
        await session.rollback()

        raise HTTPException(
            status_code=(status.HTTP_503_SERVICE_UNAVAILABLE),
            detail=("Meta webhook credentials are unavailable."),
        ) from exc

    return Response(
        status_code=status.HTTP_200_OK,
    )
