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
from app.integrations.vault.client import (
    VaultClient,
)
from app.integrations.vault.paths import (
    VaultPathBuilder,
)
from app.repositories.business_audit_log import (
    BusinessAuditLogRepository,
)
from app.repositories.integration import (
    IntegrationRepository,
)
from app.services.integration_credentials import (
    IntegrationCredentialInvalidError,
    IntegrationCredentialRotationService,
)


@pytest.mark.asyncio
async def test_meta_credentials_are_written_to_tenant_vault_namespace() -> None:
    tenant_id = uuid4()
    integration_id = uuid4()

    integration = Integration(
        id=integration_id,
        tenant_id=tenant_id,
        provider=(IntegrationProvider.META),
        name="Meta",
        config_json={},
        vault_secret_reference=None,
        active=True,
    )

    repository = MagicMock(spec=IntegrationRepository)

    repository.get_by_id = AsyncMock(return_value=integration)

    repository.flush = AsyncMock()

    audit_repository = MagicMock(spec=BusinessAuditLogRepository)

    vault_client = AsyncMock(spec=VaultClient)

    service = IntegrationCredentialRotationService(
        repository=repository,
        audit_repository=(audit_repository),
        vault_client=vault_client,
        path_builder=(VaultPathBuilder()),
    )

    result = await service.rotate(
        integration_id=integration_id,
        context=AuthorizationContext(
            actor_id="tenant-admin",
            role=Role.TENANT_ADMIN,
            tenant_id=tenant_id,
        ),
        actor_id="tenant-admin",
        trace_id="trace-123",
        secret_values={
            "access_token": "token",
            "app_secret": "app-secret",
            "verify_token": "verify",
        },
    )

    assert result.credentials_configured is True

    written_path = vault_client.write_secret.await_args.kwargs["path"]

    assert written_path.startswith(
        (f"whatsapp-platform/tenants/{tenant_id}/meta/{integration_id}/credentials/")
    )

    repository.set_vault_secret_reference.assert_called_once_with(
        integration=integration,
        reference=written_path,
    )

    vault_client.write_secret.assert_awaited_once()

    audit_repository.add_integration_credentials_rotated.assert_called_once_with(
        integration_id=integration_id,
        provider=(IntegrationProvider.META),
        actor_id="tenant-admin",
        trace_id="trace-123",
        previously_configured=False,
    )


@pytest.mark.asyncio
async def test_invalid_meta_credentials_are_not_written_to_vault() -> None:
    tenant_id = uuid4()

    integration = Integration(
        id=uuid4(),
        tenant_id=tenant_id,
        provider=(IntegrationProvider.META),
        name="Meta",
        config_json={},
        active=True,
    )

    repository = MagicMock(spec=IntegrationRepository)

    repository.get_by_id = AsyncMock(return_value=integration)

    vault_client = AsyncMock(spec=VaultClient)

    service = IntegrationCredentialRotationService(
        repository=repository,
        audit_repository=MagicMock(spec=(BusinessAuditLogRepository)),
        vault_client=vault_client,
        path_builder=(VaultPathBuilder()),
    )

    with pytest.raises(IntegrationCredentialInvalidError):
        await service.rotate(
            integration_id=(integration.id),
            context=AuthorizationContext(
                actor_id="tenant-admin",
                role=Role.TENANT_ADMIN,
                tenant_id=tenant_id,
            ),
            actor_id="tenant-admin",
            trace_id="trace",
            secret_values={
                "access_token": "token",
            },
        )

    vault_client.write_secret.assert_not_awaited()
