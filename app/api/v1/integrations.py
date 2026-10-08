from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    status,
)
from pydantic import (
    BaseModel,
    SecretStr,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from app.api.dependencies.database import (
    get_db_session,
)
from app.api.rate_limits import (
    require_integration_admin_rate_limit,
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
from app.db.models.security_access_log import (
    SecurityAccessOutcome,
    SecurityPrincipalType,
)
from app.integrations.vault.client import (
    VaultClient,
    VaultClientConfig,
)
from app.integrations.vault.paths import (
    VaultPathBuilder,
)
from app.repositories.business_audit_log import (
    BusinessAuditLogRepository,
)
from app.repositories.integration import (
    IntegrationRepository,
)
from app.security_access import (
    get_request_trace_id,
    record_security_access,
)
from app.services.integration_credentials import (
    IntegrationCredentialInvalidError,
    IntegrationCredentialNotFoundError,
    IntegrationCredentialPersistenceError,
    IntegrationCredentialRotationService,
    IntegrationCredentialVaultError,
)


router = APIRouter(
    prefix="/integrations",
    tags=["integrations"],
)


class IntegrationCredentialUpdateRequest(BaseModel):
    access_token: SecretStr | None = None
    app_secret: SecretStr | None = None
    verify_token: SecretStr | None = None
    api_key: SecretStr | None = None


class IntegrationCredentialResponse(BaseModel):
    integration_id: UUID
    provider: IntegrationProvider
    credentials_configured: bool


@router.post(
    "/{integration_id}/credentials",
    response_model=IntegrationCredentialResponse,
    dependencies=[
        Depends(require_integration_admin_rate_limit),
    ],
)
async def update_integration_credentials(
    integration_id: UUID,
    payload: IntegrationCredentialUpdateRequest,
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
) -> IntegrationCredentialResponse:
    settings = get_settings()

    vault_client = VaultClient(
        VaultClientConfig(
            url=settings.vault_addr,
            token=settings.vault_token,
            namespace=settings.vault_namespace,
            verify=settings.vault_verify,
            timeout_seconds=settings.vault_timeout_seconds,
            kv_mount_point=settings.vault_kv_mount_point,
        )
    )

    repository = IntegrationRepository(
        session=session,
        tenant=request_context.tenant,
    )

    audit_repository = BusinessAuditLogRepository(
        session=session,
        tenant=request_context.tenant,
    )

    service = IntegrationCredentialRotationService(
        repository=repository,
        audit_repository=audit_repository,
        vault_client=vault_client,
        path_builder=VaultPathBuilder(
            root=settings.vault_path_root,
        ),
    )

    secret_values = _secret_values(payload)

    trace_id = get_request_trace_id(request)

    try:
        result = await service.rotate(
            integration_id=integration_id,
            context=request_context.authorization,
            actor_id=request_context.principal.subject,
            trace_id=trace_id,
            secret_values=secret_values,
        )

        await session.commit()

    except IntegrationCredentialNotFoundError as exc:
        await session.rollback()

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "INTEGRATION_NOT_FOUND",
                "message": "Integration was not found.",
                "trace_id": trace_id,
            },
        ) from exc

    except (
        AuthorizationDeniedError,
        TenantIsolationError,
    ) as exc:
        await session.rollback()

        await record_security_access(
            request=request,
            principal_type=SecurityPrincipalType.HUMAN,
            principal_id=request_context.principal.subject,
            tenant_id=request_context.tenant.tenant_id,
            event="authorization.denied",
            outcome=SecurityAccessOutcome.DENIED,
            resource_type="integration",
            resource_id=str(integration_id),
            reason_code=("integration_credentials_update_not_allowed"),
        )

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "INTEGRATION_CREDENTIALS_FORBIDDEN",
                "message": ("Integration credential update is not allowed."),
                "trace_id": trace_id,
            },
        ) from exc

    except IntegrationCredentialInvalidError as exc:
        await session.rollback()

        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "INVALID_INTEGRATION_CREDENTIALS",
                "message": str(exc),
                "trace_id": trace_id,
            },
        ) from exc

    except IntegrationCredentialVaultError as exc:
        await session.rollback()

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "VAULT_UNAVAILABLE",
                "message": ("Credential storage is temporarily unavailable."),
                "trace_id": trace_id,
            },
        ) from exc

    except IntegrationCredentialPersistenceError as exc:
        await session.rollback()

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "CREDENTIAL_PERSISTENCE_FAILED",
                "message": ("Credential update could not be completed."),
                "trace_id": trace_id,
            },
        ) from exc

    finally:
        await vault_client.close()

    return IntegrationCredentialResponse(
        integration_id=result.integration_id,
        provider=result.provider,
        credentials_configured=result.credentials_configured,
    )


def _secret_values(
    payload: IntegrationCredentialUpdateRequest,
) -> dict[str, str]:
    result: dict[str, str] = {}

    if payload.access_token is not None:
        result["access_token"] = payload.access_token.get_secret_value()

    if payload.app_secret is not None:
        result["app_secret"] = payload.app_secret.get_secret_value()

    if payload.verify_token is not None:
        result["verify_token"] = payload.verify_token.get_secret_value()

    if payload.api_key is not None:
        result["api_key"] = payload.api_key.get_secret_value()

    return result
