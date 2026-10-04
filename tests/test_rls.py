from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.rls import apply_tenant_rls_context
from app.tenants.context import (
    TenantContext,
    TenantContextSource,
)


@pytest.mark.asyncio
async def test_apply_tenant_rls_context_sets_tenant_id() -> None:
    tenant_id = uuid4()

    context = TenantContext(
        tenant_id=tenant_id,
        slug="tenant-a",
        source=TenantContextSource.AUTHENTICATED_SESSION,
    )

    session = AsyncMock(spec=AsyncSession)

    await apply_tenant_rls_context(
        session,
        context,
    )

    session.execute.assert_awaited_once()
