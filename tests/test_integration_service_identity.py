from __future__ import annotations

from unittest.mock import (
    AsyncMock,
    MagicMock,
)
from uuid import uuid4

import pytest
from sqlalchemy import (
    UniqueConstraint,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from app.db.models.integration import (
    Integration,
    IntegrationProvider,
)
from app.repositories.integration import (
    ServiceIntegrationIdentityRepository,
)


def test_integration_has_keycloak_client_id_column() -> None:
    column = Integration.__table__.columns["keycloak_client_id"]

    assert column.nullable

    assert column.type.length == 255


def test_keycloak_client_id_is_globally_unique() -> None:
    constraint_names = {
        constraint.name
        for constraint in Integration.__table__.constraints
        if isinstance(
            constraint,
            UniqueConstraint,
        )
    }

    assert "uq_integrations_keycloak_client_id" in constraint_names


@pytest.mark.asyncio
async def test_service_identity_repository_resolves_active_integration() -> None:
    tenant_id = uuid4()

    integration = Integration(
        id=uuid4(),
        tenant_id=tenant_id,
        provider=(IntegrationProvider.ODOO),
        name="Odoo",
        keycloak_client_id=("tenant-a-odoo"),
        config_json={},
        active=True,
    )

    scalar_result = MagicMock()

    scalar_result.first.return_value = integration

    session = AsyncMock(spec=AsyncSession)

    session.scalars.return_value = scalar_result

    repository = ServiceIntegrationIdentityRepository(session=session)

    result = await repository.get_active_by_keycloak_client_id(client_id=("tenant-a-odoo"))

    assert result is integration

    session.scalars.assert_awaited_once()


@pytest.mark.asyncio
async def test_service_identity_repository_strips_client_id() -> None:
    integration = Integration(
        id=uuid4(),
        tenant_id=uuid4(),
        provider=(IntegrationProvider.ODOO),
        name="Odoo",
        keycloak_client_id=("tenant-a-odoo"),
        config_json={},
        active=True,
    )

    scalar_result = MagicMock()

    scalar_result.first.return_value = integration

    session = AsyncMock(spec=AsyncSession)

    session.scalars.return_value = scalar_result

    repository = ServiceIntegrationIdentityRepository(session=session)

    result = await repository.get_active_by_keycloak_client_id(client_id=("  tenant-a-odoo  "))

    assert result is integration

    statement = session.scalars.await_args.args[0]

    compiled = str(statement)

    assert "keycloak_client_id" in compiled

    assert "integrations.active" in compiled


@pytest.mark.asyncio
async def test_blank_service_client_id_is_rejected_without_database_query() -> None:
    session = AsyncMock(spec=AsyncSession)

    repository = ServiceIntegrationIdentityRepository(session=session)

    result = await repository.get_active_by_keycloak_client_id(client_id="   ")

    assert result is None

    session.scalars.assert_not_awaited()
