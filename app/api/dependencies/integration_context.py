from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import (
    Depends,
    HTTPException,
    status,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from app.api.dependencies.database import (
    get_db_session,
)
from app.api.dependencies.service_auth import (
    require_service_principal,
)
from app.auth.service_token import (
    ServicePrincipal,
)
from app.authorization.context import (
    AuthorizationContext,
)
from app.authorization.roles import (
    Role,
)
from app.db.models.integration import (
    Integration,
)
from app.db.rls import (
    apply_tenant_rls_context,
)
from app.repositories.integration import (
    ServiceIntegrationIdentityRepository,
)
from app.tenants.context import (
    TenantContext,
    TenantContextSource,
)


WEBHOOK_MANAGE_SCOPE = "webhook:manage"


@dataclass(
    frozen=True,
    slots=True,
)
class IntegrationRequestContext:
    principal: ServicePrincipal
    integration: Integration
    tenant: TenantContext
    authorization: AuthorizationContext


async def resolve_integration_request_context(
    *,
    principal: ServicePrincipal,
    session: AsyncSession,
) -> IntegrationRequestContext:
    repository = ServiceIntegrationIdentityRepository(session=session)

    integration = await repository.get_active_by_keycloak_client_id(client_id=(principal.client_id))

    if integration is None:
        raise HTTPException(
            status_code=(status.HTTP_403_FORBIDDEN),
            detail={
                "code": ("SERVICE_INTEGRATION_NOT_REGISTERED"),
                "message": (
                    "The authenticated service identity is not registered as an active integration."
                ),
            },
        )

    tenant = await repository.get_active_tenant_by_id(tenant_id=(integration.tenant_id))

    if tenant is None:
        raise HTTPException(
            status_code=(status.HTTP_403_FORBIDDEN),
            detail={
                "code": ("SERVICE_INTEGRATION_TENANT_UNAVAILABLE"),
                "message": ("The integration tenant is not active."),
            },
        )

    tenant_context = TenantContext.from_tenant(
        tenant,
        source=(TenantContextSource.INTEGRATION),
    )

    # From this point onward, normal tenant-owned
    # repositories execute under the same PostgreSQL
    # tenant context used by human requests.
    await apply_tenant_rls_context(
        session,
        tenant_context,
    )

    authorization = AuthorizationContext(
        actor_id=(principal.client_id),
        role=Role.INTEGRATION,
        tenant_id=(tenant_context.tenant_id),
    )

    return IntegrationRequestContext(
        principal=principal,
        integration=integration,
        tenant=tenant_context,
        authorization=authorization,
    )


async def require_integration_request_context(
    principal: Annotated[
        ServicePrincipal,
        Depends(require_service_principal),
    ],
    session: Annotated[
        AsyncSession,
        Depends(get_db_session),
    ],
) -> IntegrationRequestContext:
    return await resolve_integration_request_context(
        principal=principal,
        session=session,
    )


async def require_webhook_manage_integration_request_context(
    principal: Annotated[
        ServicePrincipal,
        Depends(require_service_principal),
    ],
    session: Annotated[
        AsyncSession,
        Depends(get_db_session),
    ],
) -> IntegrationRequestContext:
    _require_service_scope(
        principal=principal,
        required_scope=(WEBHOOK_MANAGE_SCOPE),
    )

    return await resolve_integration_request_context(
        principal=principal,
        session=session,
    )


def _require_service_scope(
    *,
    principal: ServicePrincipal,
    required_scope: str,
) -> None:
    if required_scope in principal.scopes:
        return

    raise HTTPException(
        status_code=(status.HTTP_403_FORBIDDEN),
        detail={
            "code": ("SERVICE_SCOPE_REQUIRED"),
            "message": ("The service identity does not have the required scope."),
            "required_scope": (required_scope),
        },
        headers={
            "WWW-Authenticate": (f'Bearer error="insufficient_scope", scope="{required_scope}"')
        },
    )
