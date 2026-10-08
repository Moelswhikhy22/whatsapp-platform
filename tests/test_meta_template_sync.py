from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.authorization.context import (
    AuthorizationContext,
)
from app.authorization.roles import Role
from app.db.models.integration import (
    Integration,
    IntegrationProvider,
)
from app.db.models.template import (
    Template,
    TemplateStatus,
    TemplateType,
)
from app.integrations.meta.outbound_credentials import (
    MetaOutboundCredentialProvider,
    MetaOutboundCredentials,
)
from app.integrations.meta.template_client import (
    MetaRemoteTemplate,
    MetaTemplateAPIClient,
)
from app.repositories.template import (
    TemplateRepository,
)
from app.services.meta_template_sync import (
    MetaTemplateSyncNotAllowedError,
    MetaTemplateSyncService,
)


def _context(
    *,
    tenant_id,
    role: Role,
) -> AuthorizationContext:
    return AuthorizationContext(
        actor_id="keycloak-user-1",
        role=role,
        tenant_id=tenant_id,
    )


def _objects():
    tenant_id = uuid4()

    integration = Integration(
        id=uuid4(),
        tenant_id=tenant_id,
        provider=IntegrationProvider.META,
        name="Meta Main",
        external_account_id="123456",
        config_json={
            "graph_api_version": "v99.0",
        },
        active=True,
    )

    template = Template(
        id=uuid4(),
        tenant_id=tenant_id,
        template_type=TemplateType.META,
        category="UTILITY",
        name=None,
        body=None,
        variables_json=None,
        active=None,
        meta_template_name=("payment_reminder"),
        language="en_US",
        components_json=[
            {
                "type": "BODY",
                "text": "Hello",
            }
        ],
        status=TemplateStatus.SUBMITTED,
        meta_account_id=integration.id,
        last_synced_at=None,
    )

    return tenant_id, integration, template


@pytest.mark.asyncio
async def test_sync_updates_submitted_to_approved() -> None:
    tenant_id, integration, template = _objects()

    synced_at = datetime(
        2026,
        10,
        13,
        9,
        0,
        tzinfo=UTC,
    )

    repository = MagicMock(spec=TemplateRepository)
    repository.tenant_id = tenant_id
    repository.get_active_meta_integration = AsyncMock(return_value=integration)
    repository.list_meta_for_account_for_update = AsyncMock(return_value=[template])

    credentials = AsyncMock(spec=MetaOutboundCredentialProvider)
    credentials.get_credentials.return_value = MetaOutboundCredentials(access_token="token")

    client = AsyncMock(spec=MetaTemplateAPIClient)
    client.fetch_templates.return_value = [
        MetaRemoteTemplate(
            provider_template_id="987",
            name="payment_reminder",
            language="en_US",
            category="UTILITY",
            status="APPROVED",
            components=[],
        )
    ]

    service = MetaTemplateSyncService(
        repository=repository,
        credential_provider=credentials,
        meta_client=client,
        clock=lambda: synced_at,
    )

    result = await service.sync(
        context=_context(
            tenant_id=tenant_id,
            role=Role.TENANT_ADMIN,
        ),
        meta_account_id=integration.id,
    )

    assert template.status is TemplateStatus.APPROVED
    assert template.last_synced_at == synced_at

    assert result.fetched_count == 1
    assert result.matched_count == 1
    assert result.updated_count == 1

    repository.add_template_audit.assert_called_once()


@pytest.mark.asyncio
async def test_pending_keeps_local_submitted() -> None:
    tenant_id, integration, template = _objects()

    repository = MagicMock(spec=TemplateRepository)
    repository.tenant_id = tenant_id
    repository.get_active_meta_integration = AsyncMock(return_value=integration)
    repository.list_meta_for_account_for_update = AsyncMock(return_value=[template])

    credentials = AsyncMock(spec=MetaOutboundCredentialProvider)
    credentials.get_credentials.return_value = MetaOutboundCredentials(access_token="token")

    client = AsyncMock(spec=MetaTemplateAPIClient)
    client.fetch_templates.return_value = [
        MetaRemoteTemplate(
            provider_template_id="987",
            name="payment_reminder",
            language="en_US",
            category="UTILITY",
            status="PENDING",
            components=[],
        )
    ]

    service = MetaTemplateSyncService(
        repository=repository,
        credential_provider=credentials,
        meta_client=client,
    )

    result = await service.sync(
        context=_context(
            tenant_id=tenant_id,
            role=Role.TENANT_ADMIN,
        ),
        meta_account_id=integration.id,
    )

    assert template.status is TemplateStatus.SUBMITTED
    assert template.last_synced_at is not None

    assert result.updated_count == 0

    repository.add_template_audit.assert_not_called()


@pytest.mark.asyncio
async def test_local_draft_is_not_promoted_by_sync() -> None:
    tenant_id, integration, template = _objects()

    template.status = TemplateStatus.DRAFT

    repository = MagicMock(spec=TemplateRepository)
    repository.tenant_id = tenant_id
    repository.get_active_meta_integration = AsyncMock(return_value=integration)
    repository.list_meta_for_account_for_update = AsyncMock(return_value=[template])

    credentials = AsyncMock(spec=MetaOutboundCredentialProvider)
    credentials.get_credentials.return_value = MetaOutboundCredentials(access_token="token")

    client = AsyncMock(spec=MetaTemplateAPIClient)
    client.fetch_templates.return_value = [
        MetaRemoteTemplate(
            provider_template_id="987",
            name="payment_reminder",
            language="en_US",
            category="UTILITY",
            status="APPROVED",
            components=[],
        )
    ]

    service = MetaTemplateSyncService(
        repository=repository,
        credential_provider=credentials,
        meta_client=client,
    )

    result = await service.sync(
        context=_context(
            tenant_id=tenant_id,
            role=Role.TENANT_ADMIN,
        ),
        meta_account_id=integration.id,
    )

    assert template.status is TemplateStatus.DRAFT
    assert result.draft_skipped_count == 1


@pytest.mark.asyncio
async def test_unknown_provider_status_is_ignored() -> None:
    tenant_id, integration, template = _objects()

    repository = MagicMock(spec=TemplateRepository)
    repository.tenant_id = tenant_id
    repository.get_active_meta_integration = AsyncMock(return_value=integration)
    repository.list_meta_for_account_for_update = AsyncMock(return_value=[template])

    credentials = AsyncMock(spec=MetaOutboundCredentialProvider)
    credentials.get_credentials.return_value = MetaOutboundCredentials(access_token="token")

    client = AsyncMock(spec=MetaTemplateAPIClient)
    client.fetch_templates.return_value = [
        MetaRemoteTemplate(
            provider_template_id="987",
            name="payment_reminder",
            language="en_US",
            category="UTILITY",
            status="IN_APPEAL",
            components=[],
        )
    ]

    service = MetaTemplateSyncService(
        repository=repository,
        credential_provider=credentials,
        meta_client=client,
    )

    result = await service.sync(
        context=_context(
            tenant_id=tenant_id,
            role=Role.TENANT_ADMIN,
        ),
        meta_account_id=integration.id,
    )

    assert template.status is TemplateStatus.SUBMITTED
    assert result.unknown_status_count == 1


@pytest.mark.asyncio
async def test_employee_cannot_sync_templates() -> None:
    tenant_id, integration, _ = _objects()

    repository = MagicMock(spec=TemplateRepository)
    repository.tenant_id = tenant_id
    repository.get_active_meta_integration = AsyncMock()

    credentials = AsyncMock(spec=MetaOutboundCredentialProvider)
    client = AsyncMock(spec=MetaTemplateAPIClient)

    service = MetaTemplateSyncService(
        repository=repository,
        credential_provider=credentials,
        meta_client=client,
    )

    with pytest.raises(MetaTemplateSyncNotAllowedError):
        await service.sync(
            context=_context(
                tenant_id=tenant_id,
                role=Role.EMPLOYEE,
            ),
            meta_account_id=integration.id,
        )

    repository.get_active_meta_integration.assert_not_awaited()
