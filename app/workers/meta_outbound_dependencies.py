from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from app.integrations.meta.client import (
    MetaCloudAPIClient,
)
from app.integrations.meta.outbound_credentials import (
    MetaOutboundCredentialProvider,
)
from app.repositories.message_status import (
    MessageStatusRepository,
)
from app.repositories.meta_outbound import (
    MetaOutboundRepository,
)
from app.services.meta_outbound import (
    MetaOutboundSendService,
)
from app.workers.meta_inbound_dependencies import (
    MetaInboundTenantNotFoundError,
    resolve_worker_tenant_context,
)


class MetaOutboundTenantNotFoundError(RuntimeError):
    pass


async def build_meta_outbound_service(
    *,
    session: AsyncSession,
    tenant_id: UUID,
    credential_provider: (MetaOutboundCredentialProvider),
    meta_client: MetaCloudAPIClient,
) -> MetaOutboundSendService:
    try:
        await resolve_worker_tenant_context(
            session=session,
            tenant_id=tenant_id,
        )
    except MetaInboundTenantNotFoundError as exc:
        raise (MetaOutboundTenantNotFoundError(f"Tenant {tenant_id} was not found.")) from exc

    repository = MetaOutboundRepository(
        session=session,
        tenant_id=tenant_id,
    )

    status_repository = MessageStatusRepository(
        session=session,
        tenant_id=tenant_id,
    )

    return MetaOutboundSendService(
        repository=repository,
        status_repository=(status_repository),
        credential_provider=(credential_provider),
        meta_client=meta_client,
    )
