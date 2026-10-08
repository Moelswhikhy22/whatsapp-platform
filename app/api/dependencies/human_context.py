from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import (
    Depends,
    HTTPException,
    Request,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.database import (
    get_db_session,
)
from app.api.dependencies.human_auth import (
    require_human_principal,
)
from app.api.dependencies.human_tenant import (
    require_human_tenant_context,
)
from app.auth.id_token import HumanPrincipal
from app.authorization.context import (
    AuthorizationContext,
)
from app.authorization.conversation import (
    ConversationActorContext,
)
from app.db.models.security_access_log import (
    SecurityAccessOutcome,
    SecurityPrincipalType,
)
from app.repositories.external_identity import (
    ExternalIdentityRepository,
)
from app.repositories.group_membership import (
    GroupMembershipRepository,
)
from app.security_access import (
    record_security_access,
)
from app.services.human_conversation_actor import (
    HumanConversationActorResolver,
)
from app.services.human_tenant_authorization import (
    HumanTenantAuthorizationResolver,
    HumanTenantMembershipNotFoundError,
    InvalidHumanTenantRoleError,
)
from app.tenants.context import TenantContext


@dataclass(
    frozen=True,
    slots=True,
)
class HumanConversationRequestContext:
    principal: HumanPrincipal
    tenant: TenantContext
    authorization: AuthorizationContext
    actor: ConversationActorContext


async def require_human_conversation_request_context(
    request: Request,
    principal: Annotated[
        HumanPrincipal,
        Depends(require_human_principal),
    ],
    tenant: Annotated[
        TenantContext,
        Depends(require_human_tenant_context),
    ],
    session: Annotated[
        AsyncSession,
        Depends(get_db_session),
    ],
) -> HumanConversationRequestContext:
    authorization_resolver = HumanTenantAuthorizationResolver(
        session,
    )

    try:
        resolved_authorization = await authorization_resolver.resolve(
            principal=principal,
            tenant_context=tenant,
        )

    except HumanTenantMembershipNotFoundError as exc:
        await record_security_access(
            request=request,
            principal_type=(SecurityPrincipalType.HUMAN),
            principal_id=principal.subject,
            tenant_id=tenant.tenant_id,
            event=("human.tenant_authorization"),
            outcome=(SecurityAccessOutcome.DENIED),
            resource_type="tenant",
            resource_id=str(tenant.tenant_id),
            reason_code=("tenant_membership_not_found"),
        )

        raise HTTPException(
            status_code=(status.HTTP_403_FORBIDDEN),
            detail=("Tenant membership is not authorized."),
        ) from exc

    except InvalidHumanTenantRoleError as exc:
        await record_security_access(
            request=request,
            principal_type=(SecurityPrincipalType.HUMAN),
            principal_id=principal.subject,
            tenant_id=tenant.tenant_id,
            event=("human.tenant_authorization"),
            outcome=(SecurityAccessOutcome.DENIED),
            resource_type="tenant",
            resource_id=str(tenant.tenant_id),
            reason_code=("invalid_tenant_role"),
        )

        raise HTTPException(
            status_code=(status.HTTP_403_FORBIDDEN),
            detail=("Tenant membership is not authorized."),
        ) from exc

    external_identity_repository = ExternalIdentityRepository(
        session=session,
        tenant=tenant,
    )

    group_membership_repository = GroupMembershipRepository(
        session=session,
        tenant=tenant,
    )

    actor_resolver = HumanConversationActorResolver(
        external_identity_repository=(external_identity_repository),
        group_membership_repository=(group_membership_repository),
    )

    actor = await actor_resolver.resolve(
        subject=principal.subject,
    )

    return HumanConversationRequestContext(
        principal=principal,
        tenant=tenant,
        authorization=(resolved_authorization.context),
        actor=actor,
    )
