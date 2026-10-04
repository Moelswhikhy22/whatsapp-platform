from unittest.mock import AsyncMock
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.tenant_domain import (
    TenantDomain,
)
from app.repositories.base import (
    TenantScopedRepository,
)
from app.tenants.context import (
    TenantContext,
    TenantContextSource,
)


def test_repository_scope_uses_tenant_context() -> None:
    tenant_id = uuid4()

    context = TenantContext(
        tenant_id=tenant_id,
        slug="tenant-a",
        source=TenantContextSource.AUTHENTICATED_SESSION,
    )

    session = AsyncMock(spec=AsyncSession)

    repository = TenantScopedRepository(
        session=session,
        tenant=context,
    )

    statement = repository._scope(  # noqa: SLF001
        select(TenantDomain),
        TenantDomain.tenant_id,
    )

    compiled = statement.compile()

    assert tenant_id in compiled.params.values()
    assert "tenant_domains.tenant_id" in str(compiled)

    def test_repository_keeps_tenant_context() -> None:
        context = TenantContext(
            tenant_id=uuid4(),
            slug="tenant-a",
        )

        session = AsyncMock(spec=AsyncSession)

        repository = TenantScopedRepository(
            session=session,
            tenant=context,
        )

        assert repository.tenant is context
        assert repository.tenant_id == context.tenant_id
