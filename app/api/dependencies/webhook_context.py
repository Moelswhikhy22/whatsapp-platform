from __future__ import annotations

from dataclasses import dataclass
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
from app.api.dependencies.human_tenant import (
    require_human_tenant_context,
)
from app.api.dependencies.integration_context import (
    require_webhook_manage_integration_request_context,
)
from app.api.dependencies.service_auth import (
    require_service_principal,
)
from app.authorization import (
    AuthorizationDeniedError,
)
from app.authorization.context import (
    AuthorizationContext,
)
from app.authorization.permissions import (
    Permission,
)
from app.authorization.policy import (
    require_permission,
)
from app.services.human_tenant_authorization import (
    HumanTenantAuthorizationResolver,
    HumanTenantMembershipNotFoundError,
    InvalidHumanTenantRoleError,
)
from app.tenants.context import (
    TenantContext,
)


@dataclass(
    frozen=True,
    slots=True,
)
class WebhookRequestContext:
    """
    Authentication-source-neutral context used by
    outgoing webhook management endpoints.

    The caller may be either:
    - a human authenticated through the BFF session, or
    - a Keycloak Client Credentials integration.
    """

    tenant: TenantContext
    authorization: AuthorizationContext


async def require_webhook_request_context(
    request: Request,
    session: Annotated[
        AsyncSession,
        Depends(get_db_session),
    ],
) -> WebhookRequestContext:
    # Explicit Authorization means machine-auth mode.
    #
    # Never silently fall back to a browser session
    # when an Authorization header was supplied but
    # is invalid.
    if request.headers.get("Authorization") is not None:
        return await _resolve_integration_context(
            request=request,
            session=session,
        )

    return await _resolve_human_context(
        request=request,
        session=session,
    )


async def _resolve_integration_context(
    *,
    request: Request,
    session: AsyncSession,
) -> WebhookRequestContext:
    principal = await require_service_principal(request)

    context = await require_webhook_manage_integration_request_context(
        principal=principal,
        session=session,
    )

    _require_webhook_permission(context.authorization)

    return WebhookRequestContext(
        tenant=context.tenant,
        authorization=(context.authorization),
    )


async def _resolve_human_context(
    *,
    request: Request,
    session: AsyncSession,
) -> WebhookRequestContext:
    principal = await require_human_principal(request)

    tenant = await require_human_tenant_context(
        request=request,
        _principal=principal,
        session=session,
    )

    authorization_resolver = HumanTenantAuthorizationResolver(session)

    try:
        resolved_authorization = await authorization_resolver.resolve(
            principal=principal,
            tenant_context=tenant,
        )

    except (
        HumanTenantMembershipNotFoundError,
        InvalidHumanTenantRoleError,
    ) as exc:
        raise _manage_forbidden() from exc

    _require_webhook_permission(resolved_authorization.context)

    return WebhookRequestContext(
        tenant=tenant,
        authorization=(resolved_authorization.context),
    )


def _require_webhook_permission(
    context: AuthorizationContext,
) -> None:
    try:
        require_permission(
            context,
            Permission.WEBHOOK_MANAGE,
        )

    except AuthorizationDeniedError as exc:
        raise _manage_forbidden() from exc


def _manage_forbidden() -> HTTPException:
    return HTTPException(
        status_code=(status.HTTP_403_FORBIDDEN),
        detail={
            "code": ("WEBHOOK_MANAGE_FORBIDDEN"),
            "message": ("Webhook management is not allowed."),
        },
    )
