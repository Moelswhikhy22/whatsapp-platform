from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.tenants.context import TenantContext


async def apply_tenant_rls_context(
    session: AsyncSession,
    tenant: TenantContext,
) -> None:
    """Set the PostgreSQL tenant context for the current transaction."""

    await session.execute(
        text(
            """
            SELECT set_config(
                'app.tenant_id',
                :tenant_id,
                true
            )
            """
        ),
        {
            "tenant_id": str(tenant.tenant_id),
        },
    )
