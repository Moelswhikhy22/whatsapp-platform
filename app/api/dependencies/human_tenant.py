from __future__ import annotations

from typing import Annotated

from fastapi import (
    Depends,
    HTTPException,
    Request,
    status,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from app.api.dependencies.database import (
    get_db_session,
)
from app.api.dependencies.human_auth import (
    require_human_principal,
)
from app.auth.id_token import HumanPrincipal
from app.db.models.security_access_log import (
    SecurityAccessOutcome,
    SecurityPrincipalType,
)
from app.db.rls import (
    apply_tenant_rls_context,
)
from app.security_access import (
    record_security_access,
)
from app.services.tenant_resolver import (
    InvalidTenantHostnameError,
    TenantNotFoundError,
    TenantResolutionConflictError,
    TenantResolver,
    TenantUnavailableError,
)
from app.tenants.context import (
    TenantContext,
)


async def require_human_tenant_context(
    request: Request,
    _principal: Annotated[
        HumanPrincipal,
        Depends(require_human_principal),
    ],
    session: Annotated[
        AsyncSession,
        Depends(get_db_session),
    ],
) -> TenantContext:
    hostname = request.url.hostname

    if hostname is None:
        raise HTTPException(
            status_code=(status.HTTP_400_BAD_REQUEST),
            detail=("Tenant hostname is required."),
        )

    resolver = TenantResolver(session)

    try:
        tenant_context = await resolver.resolve_context_by_hostname(
            hostname,
        )

    except InvalidTenantHostnameError as exc:
        raise HTTPException(
            status_code=(status.HTTP_400_BAD_REQUEST),
            detail=("Tenant hostname is invalid."),
        ) from exc

    except TenantNotFoundError as exc:
        raise HTTPException(
            status_code=(status.HTTP_404_NOT_FOUND),
            detail=("Tenant was not found."),
        ) from exc

    except TenantUnavailableError as exc:
        await record_security_access(
            request=request,
            principal_type=(SecurityPrincipalType.HUMAN),
            principal_id=_principal.subject,
            tenant_id=exc.tenant_id,
            event="human.tenant_resolution",
            outcome=(SecurityAccessOutcome.DENIED),
            resource_type="tenant",
            resource_id=str(exc.tenant_id),
            reason_code=("tenant_unavailable"),
        )

        raise HTTPException(
            status_code=(status.HTTP_403_FORBIDDEN),
            detail=("Tenant is unavailable."),
        ) from exc

    except TenantResolutionConflictError as exc:
        await record_security_access(
            request=request,
            principal_type=(SecurityPrincipalType.HUMAN),
            principal_id=_principal.subject,
            tenant_id=None,
            event="human.tenant_resolution",
            outcome=(SecurityAccessOutcome.FAILURE),
            resource_type="tenant",
            resource_id=None,
            reason_code=("tenant_resolution_conflict"),
        )

        raise HTTPException(
            status_code=(status.HTTP_500_INTERNAL_SERVER_ERROR),
            detail=("Tenant resolution failed."),
        ) from exc

    # Only attach a tenant to observability after
    # trusted server-side tenant resolution succeeds.
    request.state.observability_tenant_id = str(tenant_context.tenant_id)

    await apply_tenant_rls_context(
        session,
        tenant_context,
    )

    return tenant_context
