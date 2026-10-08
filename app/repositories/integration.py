from __future__ import annotations

from uuid import UUID

from sqlalchemy import (
    Select,
    select,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from app.db.models.integration import (
    Integration,
)
from app.db.models.tenant import (
    Tenant,
    TenantStatus,
)
from app.db.models.whatsapp_number import (
    WhatsAppNumber,
)
from app.repositories.base import (
    TenantScopedRepository,
)


class IntegrationRepository(TenantScopedRepository):
    async def get_by_id(
        self,
        integration_id: UUID,
    ) -> Integration | None:
        statement: Select[Integration] = self._scope(
            select(Integration),
            Integration.tenant_id,
        ).where(Integration.id == integration_id)

        result = await self._session.scalars(statement)

        return result.first()

    async def list_active_whatsapp_numbers(
        self,
        integration_id: UUID,
    ) -> list[WhatsAppNumber]:
        statement: Select[WhatsAppNumber] = (
            self._scope(
                select(WhatsAppNumber),
                (WhatsAppNumber.tenant_id),
            )
            .where(
                (WhatsAppNumber.integration_id == integration_id),
                (WhatsAppNumber.active.is_(True)),
            )
            .order_by(WhatsAppNumber.id.asc())
        )

        result = await self._session.scalars(statement)

        return list(result.all())

    def set_vault_secret_reference(
        self,
        *,
        integration: Integration,
        reference: str,
    ) -> None:
        integration.vault_secret_reference = reference

    async def flush(self) -> None:
        await self._session.flush()


class ServiceIntegrationIdentityRepository:
    """
    Trusted pre-tenant identity lookup.

    This repository intentionally does not inherit
    TenantScopedRepository because tenant context
    does not exist yet.

    It resolves a globally unique Keycloak service
    client ID to one active Integration and then
    resolves that Integration's active Tenant.

    It must not be used for normal tenant business
    queries.
    """

    def __init__(
        self,
        *,
        session: AsyncSession,
    ) -> None:
        self._session = session

    async def get_active_by_keycloak_client_id(
        self,
        *,
        client_id: str,
    ) -> Integration | None:
        normalized_client_id = client_id.strip()

        if not normalized_client_id:
            return None

        statement: Select[Integration] = (
            select(Integration)
            .where(
                (Integration.keycloak_client_id == normalized_client_id),
                (Integration.active.is_(True)),
            )
            .limit(1)
        )

        result = await self._session.scalars(statement)

        return result.first()

    async def get_active_tenant_by_id(
        self,
        *,
        tenant_id: UUID,
    ) -> Tenant | None:
        statement: Select[Tenant] = (
            select(Tenant)
            .where(
                Tenant.id == tenant_id,
                Tenant.status == TenantStatus.ACTIVE,
            )
            .limit(1)
        )

        result = await self._session.scalars(statement)

        return result.first()
