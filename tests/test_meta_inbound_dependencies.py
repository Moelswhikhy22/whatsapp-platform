from __future__ import annotations

from unittest.mock import (
    AsyncMock,
    MagicMock,
)
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from app.db.models.tenant import (
    Tenant,
    TenantStatus,
)
from app.presence import PresenceStore
from app.services.incoming_message import (
    IncomingMessageProcessor,
)
from app.services.message_status import (
    MessageStatusProcessor,
)
from app.tenants.context import (
    TenantContextSource,
)
from app.workers.meta_inbound_dependencies import (
    UnmappedCustomerCompanyResolver,
    build_meta_inbound_processors,
)


@pytest.mark.asyncio
async def test_unmapped_customer_company_returns_none() -> None:
    resolver = UnmappedCustomerCompanyResolver()

    result = await resolver.resolve_company_id(
        tenant_id=uuid4(),
        normalized_phone="201234567890",
        display_name="Ahmed",
    )

    assert result is None


@pytest.mark.asyncio
async def test_build_processors_uses_provider_tenant_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = uuid4()

    tenant = MagicMock(spec=Tenant)

    tenant.id = tenant_id
    tenant.slug = "tenant-a"
    tenant.status = TenantStatus.ACTIVE

    scalars = MagicMock()
    scalars.first.return_value = tenant

    session = MagicMock(spec=AsyncSession)

    session.scalars = AsyncMock(return_value=scalars)

    apply_rls = AsyncMock()

    monkeypatch.setattr(
        ("app.workers.meta_inbound_dependencies.apply_tenant_rls_context"),
        apply_rls,
    )

    presence_store = MagicMock(spec=PresenceStore)

    (
        message_processor,
        status_processor,
    ) = await build_meta_inbound_processors(
        session=session,
        tenant_id=tenant_id,
        presence_store=presence_store,
    )

    assert isinstance(
        message_processor,
        IncomingMessageProcessor,
    )

    assert isinstance(
        status_processor,
        MessageStatusProcessor,
    )

    apply_rls.assert_awaited_once()

    tenant_context = apply_rls.await_args.args[1]

    assert tenant_context.tenant_id == tenant_id

    assert tenant_context.slug == "tenant-a"

    assert tenant_context.source is (TenantContextSource.PROVIDER_IDENTITY)
