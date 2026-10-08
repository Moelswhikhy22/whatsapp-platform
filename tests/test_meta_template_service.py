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
from app.repositories.template import (
    TemplateRepository,
)
from app.services.meta_template import (
    MetaTemplateIdentityConflictError,
    MetaTemplateIntegrationNotFoundError,
    MetaTemplateInvalidDraftError,
    MetaTemplateNotAllowedError,
    MetaTemplateService,
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


def _integration(
    *,
    tenant_id,
) -> Integration:
    return Integration(
        id=uuid4(),
        tenant_id=tenant_id,
        provider=IntegrationProvider.META,
        name="Meta Main",
        config_json={},
        active=True,
    )


def _template(
    *,
    tenant_id,
    integration_id,
) -> Template:
    return Template(
        id=uuid4(),
        tenant_id=tenant_id,
        template_type=TemplateType.META,
        category="utility",
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
        meta_account_id=integration_id,
        last_synced_at=None,
    )


@pytest.mark.asyncio
async def test_tenant_admin_can_create_meta_draft() -> None:
    tenant_id = uuid4()

    integration = _integration(tenant_id=tenant_id)

    template = _template(
        tenant_id=tenant_id,
        integration_id=integration.id,
    )

    repository = MagicMock(spec=TemplateRepository)
    repository.tenant_id = tenant_id

    repository.get_active_meta_integration = AsyncMock(
        return_value=integration,
    )

    repository.get_meta_by_identity = AsyncMock(
        return_value=None,
    )

    repository.add_meta_draft.return_value = template

    service = MetaTemplateService(repository)

    result = await service.create_draft(
        context=_context(
            tenant_id=tenant_id,
            role=Role.TENANT_ADMIN,
        ),
        meta_account_id=integration.id,
        meta_template_name=("payment_reminder"),
        language="en_US",
        category="utility",
        components=[
            {
                "type": "BODY",
                "text": "Hello {{1}}",
            }
        ],
    )

    assert result is template
    assert result.status is TemplateStatus.DRAFT

    repository.add_meta_draft.assert_called_once_with(
        meta_account_id=integration.id,
        meta_template_name=("payment_reminder"),
        language="en_US",
        category="utility",
        components=[
            {
                "type": "BODY",
                "text": "Hello {{1}}",
            }
        ],
    )

    repository.add_template_audit.assert_called_once()


@pytest.mark.asyncio
async def test_employee_cannot_create_meta_draft() -> None:
    tenant_id = uuid4()

    repository = MagicMock(spec=TemplateRepository)
    repository.tenant_id = tenant_id

    repository.get_active_meta_integration = AsyncMock()

    service = MetaTemplateService(repository)

    with pytest.raises(MetaTemplateNotAllowedError):
        await service.create_draft(
            context=_context(
                tenant_id=tenant_id,
                role=Role.EMPLOYEE,
            ),
            meta_account_id=uuid4(),
            meta_template_name="welcome",
            language="en_US",
            category="utility",
            components=[
                {
                    "type": "BODY",
                }
            ],
        )

    repository.get_active_meta_integration.assert_not_awaited()


@pytest.mark.asyncio
async def test_inactive_or_missing_meta_integration_is_rejected() -> None:
    tenant_id = uuid4()

    repository = MagicMock(spec=TemplateRepository)
    repository.tenant_id = tenant_id

    repository.get_active_meta_integration = AsyncMock(
        return_value=None,
    )

    service = MetaTemplateService(repository)

    with pytest.raises(MetaTemplateIntegrationNotFoundError):
        await service.create_draft(
            context=_context(
                tenant_id=tenant_id,
                role=Role.TENANT_ADMIN,
            ),
            meta_account_id=uuid4(),
            meta_template_name="welcome",
            language="en_US",
            category="utility",
            components=[
                {
                    "type": "BODY",
                }
            ],
        )

    repository.add_meta_draft.assert_not_called()


@pytest.mark.asyncio
async def test_duplicate_meta_identity_is_rejected() -> None:
    tenant_id = uuid4()

    integration = _integration(tenant_id=tenant_id)

    existing = _template(
        tenant_id=tenant_id,
        integration_id=integration.id,
    )

    repository = MagicMock(spec=TemplateRepository)
    repository.tenant_id = tenant_id

    repository.get_active_meta_integration = AsyncMock(
        return_value=integration,
    )

    repository.get_meta_by_identity = AsyncMock(
        return_value=existing,
    )

    service = MetaTemplateService(repository)

    with pytest.raises(MetaTemplateIdentityConflictError):
        await service.create_draft(
            context=_context(
                tenant_id=tenant_id,
                role=Role.TENANT_ADMIN,
            ),
            meta_account_id=integration.id,
            meta_template_name=("payment_reminder"),
            language="en_US",
            category="utility",
            components=[
                {
                    "type": "BODY",
                }
            ],
        )

    repository.add_meta_draft.assert_not_called()


@pytest.mark.asyncio
async def test_component_without_type_is_rejected() -> None:
    tenant_id = uuid4()

    repository = MagicMock(spec=TemplateRepository)
    repository.tenant_id = tenant_id

    repository.get_active_meta_integration = AsyncMock()

    service = MetaTemplateService(repository)

    with pytest.raises(MetaTemplateInvalidDraftError):
        await service.create_draft(
            context=_context(
                tenant_id=tenant_id,
                role=Role.TENANT_ADMIN,
            ),
            meta_account_id=uuid4(),
            meta_template_name="welcome",
            language="en_US",
            category="utility",
            components=[
                {
                    "text": "Hello",
                }
            ],
        )

    repository.get_active_meta_integration.assert_not_awaited()


@pytest.mark.asyncio
async def test_cross_tenant_context_is_denied() -> None:
    tenant_id = uuid4()
    other_tenant_id = uuid4()

    repository = MagicMock(spec=TemplateRepository)
    repository.tenant_id = tenant_id

    repository.get_active_meta_integration = AsyncMock()

    service = MetaTemplateService(repository)

    with pytest.raises(MetaTemplateNotAllowedError):
        await service.create_draft(
            context=_context(
                tenant_id=other_tenant_id,
                role=Role.TENANT_ADMIN,
            ),
            meta_account_id=uuid4(),
            meta_template_name="welcome",
            language="en_US",
            category="utility",
            components=[
                {
                    "type": "BODY",
                }
            ],
        )

    repository.get_active_meta_integration.assert_not_awaited()
