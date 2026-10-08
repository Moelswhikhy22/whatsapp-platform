from __future__ import annotations

from unittest.mock import (
    AsyncMock,
    MagicMock,
)
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
    MetaTemplateAPIClient,
    MetaTemplateAPIRetryableError,
    MetaTemplateSubmissionResult,
)
from app.repositories.template import (
    TemplateRepository,
)
from app.services.meta_template_submission import (
    MetaTemplateSubmissionInvalidStateError,
    MetaTemplateSubmissionNotAllowedError,
    MetaTemplateSubmissionService,
    MetaTemplateSubmissionUnavailableError,
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
                "text": "Hello {{1}}",
            }
        ],
        status=TemplateStatus.DRAFT,
        meta_account_id=integration.id,
        last_synced_at=None,
    )

    return (
        tenant_id,
        integration,
        template,
    )


@pytest.mark.asyncio
async def test_success_marks_template_submitted() -> None:
    (
        tenant_id,
        integration,
        template,
    ) = _objects()

    repository = MagicMock(spec=TemplateRepository)
    repository.tenant_id = tenant_id
    repository.lock_meta = AsyncMock(return_value=template)
    repository.get_active_meta_integration = AsyncMock(return_value=integration)

    credential_provider = AsyncMock(spec=MetaOutboundCredentialProvider)
    credential_provider.get_credentials.return_value = MetaOutboundCredentials(access_token="token")

    meta_client = AsyncMock(spec=MetaTemplateAPIClient)
    meta_client.submit_template.return_value = MetaTemplateSubmissionResult(
        provider_template_id="987",
        provider_status="PENDING",
    )

    service = MetaTemplateSubmissionService(
        repository=repository,
        credential_provider=(credential_provider),
        meta_client=meta_client,
    )

    result = await service.submit(
        template_id=template.id,
        context=_context(
            tenant_id=tenant_id,
            role=Role.TENANT_ADMIN,
        ),
    )

    assert result.template.status is TemplateStatus.SUBMITTED
    assert result.template.last_synced_at is not None

    repository.add_template_audit.assert_called_once()


@pytest.mark.asyncio
async def test_non_draft_cannot_be_submitted() -> None:
    (
        tenant_id,
        _,
        template,
    ) = _objects()

    template.status = TemplateStatus.SUBMITTED

    repository = MagicMock(spec=TemplateRepository)
    repository.tenant_id = tenant_id
    repository.lock_meta = AsyncMock(return_value=template)

    credential_provider = AsyncMock(spec=MetaOutboundCredentialProvider)
    meta_client = AsyncMock(spec=MetaTemplateAPIClient)

    service = MetaTemplateSubmissionService(
        repository=repository,
        credential_provider=(credential_provider),
        meta_client=meta_client,
    )

    with pytest.raises(MetaTemplateSubmissionInvalidStateError):
        await service.submit(
            template_id=template.id,
            context=_context(
                tenant_id=tenant_id,
                role=Role.TENANT_ADMIN,
            ),
        )

    meta_client.submit_template.assert_not_awaited()


@pytest.mark.asyncio
async def test_employee_cannot_submit_template() -> None:
    (
        tenant_id,
        _,
        template,
    ) = _objects()

    repository = MagicMock(spec=TemplateRepository)
    repository.tenant_id = tenant_id
    repository.lock_meta = AsyncMock(return_value=template)

    credential_provider = AsyncMock(spec=MetaOutboundCredentialProvider)
    meta_client = AsyncMock(spec=MetaTemplateAPIClient)

    service = MetaTemplateSubmissionService(
        repository=repository,
        credential_provider=(credential_provider),
        meta_client=meta_client,
    )

    with pytest.raises(MetaTemplateSubmissionNotAllowedError):
        await service.submit(
            template_id=template.id,
            context=_context(
                tenant_id=tenant_id,
                role=Role.EMPLOYEE,
            ),
        )

    meta_client.submit_template.assert_not_awaited()


@pytest.mark.asyncio
async def test_transient_meta_failure_leaves_draft() -> None:
    (
        tenant_id,
        integration,
        template,
    ) = _objects()

    repository = MagicMock(spec=TemplateRepository)
    repository.tenant_id = tenant_id
    repository.lock_meta = AsyncMock(return_value=template)
    repository.get_active_meta_integration = AsyncMock(return_value=integration)

    credential_provider = AsyncMock(spec=MetaOutboundCredentialProvider)
    credential_provider.get_credentials.return_value = MetaOutboundCredentials(access_token="token")

    meta_client = AsyncMock(spec=MetaTemplateAPIClient)
    meta_client.submit_template.side_effect = MetaTemplateAPIRetryableError("temporary")

    service = MetaTemplateSubmissionService(
        repository=repository,
        credential_provider=(credential_provider),
        meta_client=meta_client,
    )

    with pytest.raises(MetaTemplateSubmissionUnavailableError):
        await service.submit(
            template_id=template.id,
            context=_context(
                tenant_id=tenant_id,
                role=Role.TENANT_ADMIN,
            ),
        )

    assert template.status is TemplateStatus.DRAFT

    repository.add_template_audit.assert_not_called()
