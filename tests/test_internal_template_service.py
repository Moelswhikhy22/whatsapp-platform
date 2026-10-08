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
from app.db.models.template import (
    Template,
    TemplateType,
)
from app.repositories.template import (
    TemplateRepository,
)
from app.services.internal_template import (
    InternalTemplateNameConflictError,
    InternalTemplateNotAllowedError,
    InternalTemplateService,
)


def _template(
    *,
    tenant_id,
    name: str = "Welcome",
) -> Template:
    return Template(
        id=uuid4(),
        tenant_id=tenant_id,
        template_type=TemplateType.INTERNAL,
        category="general",
        name=name,
        body="Hello {{1}}",
        variables_json=["name"],
        active=True,
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


@pytest.mark.asyncio
async def test_tenant_admin_can_create_internal_template() -> None:
    tenant_id = uuid4()

    repository = MagicMock(spec=TemplateRepository)
    repository.tenant_id = tenant_id

    repository.get_internal_by_name = AsyncMock(
        return_value=None,
    )

    template = _template(tenant_id=tenant_id)

    repository.add_internal.return_value = template

    service = InternalTemplateService(repository)

    result = await service.create_internal(
        context=_context(
            tenant_id=tenant_id,
            role=Role.TENANT_ADMIN,
        ),
        name="Welcome",
        category="general",
        body="Hello {{1}}",
        variables=["name"],
    )

    assert result is template

    repository.add_internal.assert_called_once_with(
        name="Welcome",
        category="general",
        body="Hello {{1}}",
        variables=["name"],
    )

    repository.add_template_audit.assert_called_once()


@pytest.mark.asyncio
async def test_employee_cannot_create_internal_template() -> None:
    tenant_id = uuid4()

    repository = MagicMock(spec=TemplateRepository)
    repository.tenant_id = tenant_id
    repository.get_internal_by_name = AsyncMock()

    service = InternalTemplateService(repository)

    with pytest.raises(InternalTemplateNotAllowedError):
        await service.create_internal(
            context=_context(
                tenant_id=tenant_id,
                role=Role.EMPLOYEE,
            ),
            name="Welcome",
            category="general",
            body="Hello",
            variables=[],
        )

    repository.get_internal_by_name.assert_not_awaited()
    repository.add_internal.assert_not_called()


@pytest.mark.asyncio
async def test_employee_can_read_internal_templates() -> None:
    tenant_id = uuid4()

    template = _template(tenant_id=tenant_id)

    repository = MagicMock(spec=TemplateRepository)
    repository.tenant_id = tenant_id
    repository.list_internal = AsyncMock(return_value=[template])

    service = InternalTemplateService(repository)

    result = await service.list_internal(
        context=_context(
            tenant_id=tenant_id,
            role=Role.EMPLOYEE,
        ),
    )

    assert result == [template]


@pytest.mark.asyncio
async def test_duplicate_internal_name_is_rejected() -> None:
    tenant_id = uuid4()

    existing = _template(tenant_id=tenant_id)

    repository = MagicMock(spec=TemplateRepository)
    repository.tenant_id = tenant_id

    repository.get_internal_by_name = AsyncMock(
        return_value=existing,
    )

    service = InternalTemplateService(repository)

    with pytest.raises(InternalTemplateNameConflictError):
        await service.create_internal(
            context=_context(
                tenant_id=tenant_id,
                role=Role.TENANT_ADMIN,
            ),
            name="Welcome",
            category="general",
            body="Hello",
            variables=[],
        )

    repository.add_internal.assert_not_called()


@pytest.mark.asyncio
async def test_group_admin_can_disable_template() -> None:
    tenant_id = uuid4()

    template = _template(tenant_id=tenant_id)

    repository = MagicMock(spec=TemplateRepository)
    repository.tenant_id = tenant_id

    repository.get_internal = AsyncMock(return_value=template)

    service = InternalTemplateService(repository)

    result = await service.update_internal(
        template_id=template.id,
        context=_context(
            tenant_id=tenant_id,
            role=Role.GROUP_ADMIN,
        ),
        changes={
            "active": False,
        },
    )

    assert result.active is False

    repository.add_template_audit.assert_called_once()

    audit_call = repository.add_template_audit.call_args.kwargs

    assert audit_call["before"]["active"] is True

    assert audit_call["after"]["active"] is False


@pytest.mark.asyncio
async def test_cross_tenant_context_is_denied() -> None:
    tenant_id = uuid4()
    other_tenant_id = uuid4()

    repository = MagicMock(spec=TemplateRepository)
    repository.tenant_id = tenant_id
    repository.list_internal = AsyncMock()

    service = InternalTemplateService(repository)

    with pytest.raises(InternalTemplateNotAllowedError):
        await service.list_internal(
            context=_context(
                tenant_id=other_tenant_id,
                role=Role.TENANT_ADMIN,
            ),
        )

    repository.list_internal.assert_not_awaited()
