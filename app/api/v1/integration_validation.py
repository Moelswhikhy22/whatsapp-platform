from __future__ import annotations

from typing import Annotated
from uuid import UUID

import httpx
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from app.api.rate_limits import require_integration_admin_rate_limit
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
from app.core.config import get_settings
from app.db.models.integration import (
    IntegrationProvider,
)
from app.integrations.meta.credential_validation import (
    MetaCredentialValidationClient,
)
from app.integrations.meta.vault_outbound_credentials import (
    VaultMetaOutboundCredentialProvider,
)
from app.integrations.vault.client import (
    VaultClient,
    VaultClientConfig,
)
from app.repositories.integration import (
    IntegrationRepository,
)
from app.services.integration_validation import (
    IntegrationValidationConfigurationError,
    IntegrationValidationNotFoundError,
    IntegrationValidationService,
    IntegrationValidationUnavailableError,
)


router = APIRouter(
    prefix="/integrations",
    tags=["integrations"],
)


class IntegrationValidationResponse(BaseModel):
    integration_id: UUID
    provider: IntegrationProvider
    valid: bool
    checked_resource_count: int
    code: str


@router.post(
    "/{integration_id}/validate",
    response_model=(IntegrationValidationResponse),
    dependencies=[
        Depends(require_integration_admin_rate_limit),
    ],
)
async def validate_integration(
    integration_id: UUID,
    request_context: Annotated[
        HumanConversationRequestContext,
        Depends(require_human_conversation_request_context),
    ],
    session: Annotated[
        AsyncSession,
        Depends(get_db_session),
    ],
) -> IntegrationValidationResponse:
    settings = get_settings()

    repository = IntegrationRepository(
        session=session,
        tenant=request_context.tenant,
    )

    vault_client = VaultClient(
        VaultClientConfig(
            url=settings.vault_addr,
            token=settings.vault_token,
            token_file=(settings.vault_token_file),
            namespace=(settings.vault_namespace),
            verify=settings.vault_verify,
            timeout_seconds=(settings.vault_timeout_seconds),
            kv_mount_point=(settings.vault_kv_mount_point),
        )
    )

    timeout = httpx.Timeout(settings.meta_http_timeout_seconds)

    try:
        async with httpx.AsyncClient(timeout=timeout) as http_client:
            service = IntegrationValidationService(
                repository=repository,
                credential_provider=(
                    VaultMetaOutboundCredentialProvider(
                        vault_client,
                        cache_ttl_seconds=(settings.vault_secret_cache_ttl_seconds),
                    )
                ),
                meta_client=(MetaCredentialValidationClient(http_client)),
            )

            try:
                result = await service.validate(
                    integration_id=(integration_id),
                    context=(request_context.authorization),
                )

            except IntegrationValidationNotFoundError as exc:
                raise HTTPException(
                    status_code=(status.HTTP_404_NOT_FOUND),
                    detail={
                        "code": ("INTEGRATION_NOT_FOUND"),
                        "message": ("Integration was not found."),
                    },
                ) from exc

            except (
                AuthorizationDeniedError,
                TenantIsolationError,
            ) as exc:
                raise HTTPException(
                    status_code=(status.HTTP_403_FORBIDDEN),
                    detail={
                        "code": ("INTEGRATION_VALIDATION_FORBIDDEN"),
                        "message": ("Integration validation is not allowed."),
                    },
                ) from exc

            except IntegrationValidationConfigurationError as exc:
                raise HTTPException(
                    status_code=(status.HTTP_422_UNPROCESSABLE_CONTENT),
                    detail={
                        "code": ("INTEGRATION_VALIDATION_CONFIGURATION_INVALID"),
                        "message": str(exc),
                    },
                ) from exc

            except IntegrationValidationUnavailableError as exc:
                raise HTTPException(
                    status_code=(status.HTTP_503_SERVICE_UNAVAILABLE),
                    detail={
                        "code": ("INTEGRATION_VALIDATION_UNAVAILABLE"),
                        "message": ("Integration validation is temporarily unavailable."),
                    },
                ) from exc

    finally:
        await vault_client.close()

    return IntegrationValidationResponse(
        integration_id=(result.integration_id),
        provider=result.provider,
        valid=result.valid,
        checked_resource_count=(result.checked_resource_count),
        code=result.code,
    )
