from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.tenant import Tenant
from app.db.rls import apply_tenant_rls_context
from app.presence import PresenceStore
from app.repositories.business_audit_log import (
    BusinessAuditLogRepository,
)
from app.repositories.conversation import (
    ConversationRepository,
)
from app.repositories.conversation_assignment_history import (
    ConversationAssignmentHistoryRepository,
)
from app.repositories.group import GroupRepository
from app.repositories.incoming_message import (
    IncomingMessageRepository,
)
from app.repositories.message_status import (
    MessageStatusRepository,
)
from app.repositories.outbox_event import (
    OutboxEventRepository,
)
from app.services.incoming_message import (
    CustomerCompanyResolver,
    IncomingMessageProcessor,
)
from app.services.message_status import (
    MessageStatusProcessor,
)
from app.services.meta_inbound_dispatcher import (
    MetaStatusProcessor,
)
from app.services.owner_unavailability import (
    OwnerUnavailabilityService,
)
from app.tenants.context import (
    TenantContext,
    TenantContextSource,
)


class MetaInboundTenantNotFoundError(RuntimeError):
    pass


class UnmappedCustomerCompanyResolver(CustomerCompanyResolver):
    """
    Safe V1 fallback for unknown customer phone numbers.

    The current domain model requires every CustomerContact to belong to a
    CustomerCompany, but the project specification does not yet define a
    trustworthy rule for deriving that company from a previously unknown
    WhatsApp sender.

    Returning None keeps the raw event UNRESOLVED rather than inventing a
    customer company or routing customer data incorrectly.
    """

    async def resolve_company_id(
        self,
        *,
        tenant_id: UUID,
        normalized_phone: str,
        display_name: str | None,
    ) -> UUID | None:
        del tenant_id
        del normalized_phone
        del display_name

        return None


async def resolve_worker_tenant_context(
    *,
    session: AsyncSession,
    tenant_id: UUID,
) -> TenantContext:
    statement = select(Tenant).where(Tenant.id == tenant_id)

    result = await session.scalars(statement)

    tenant = result.first()

    if tenant is None:
        raise MetaInboundTenantNotFoundError(f"Tenant {tenant_id} was not found.")

    tenant_context = TenantContext.from_tenant(
        tenant,
        source=(TenantContextSource.PROVIDER_IDENTITY),
    )

    await apply_tenant_rls_context(
        session,
        tenant_context,
    )

    return tenant_context


async def build_meta_inbound_processors(
    *,
    session: AsyncSession,
    tenant_id: UUID,
    presence_store: PresenceStore,
) -> tuple[
    IncomingMessageProcessor,
    MetaStatusProcessor,
]:
    tenant_context = await resolve_worker_tenant_context(
        session=session,
        tenant_id=tenant_id,
    )

    conversation_repository = ConversationRepository(
        session=session,
        tenant=tenant_context,
    )

    group_repository = GroupRepository(
        session=session,
        tenant=tenant_context,
    )

    assignment_history_repository = ConversationAssignmentHistoryRepository(
        session=session,
        tenant=tenant_context,
    )

    audit_repository = BusinessAuditLogRepository(
        session=session,
        tenant=tenant_context,
    )

    outbox_repository = OutboxEventRepository(
        session=session,
        tenant=tenant_context,
    )

    owner_unavailability_service = OwnerUnavailabilityService(
        conversation_repository=(conversation_repository),
        group_repository=group_repository,
        assignment_history_repository=(assignment_history_repository),
        audit_repository=audit_repository,
        outbox_repository=outbox_repository,
        presence_store=presence_store,
    )

    message_processor = IncomingMessageProcessor(
        repository=(
            IncomingMessageRepository(
                session=session,
                tenant_id=tenant_id,
            )
        ),
        customer_company_resolver=(UnmappedCustomerCompanyResolver()),
        owner_unavailability_handler=(owner_unavailability_service),
    )

    status_processor = MessageStatusProcessor(
        repository=(
            MessageStatusRepository(
                session=session,
                tenant_id=tenant_id,
            )
        ),
    )

    return (
        message_processor,
        status_processor,
    )
