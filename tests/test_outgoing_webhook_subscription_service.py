from __future__ import annotations

from types import SimpleNamespace
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
from app.integrations.vault.client import (
    VaultClient,
)
from app.integrations.vault.paths import (
    VaultPathBuilder,
)
from app.integrations.webhooks.ssrf import (
    WebhookEndpointValidator,
)
from app.repositories.business_audit_log import (
    BusinessAuditLogRepository,
)
from app.repositories.outgoing_webhook import (
    OutgoingWebhookRepository,
)
from app.services.outgoing_webhook_subscription import (
    OutgoingWebhookSubscriptionInvalidError,
    OutgoingWebhookSubscriptionService,
)


@pytest.mark.asyncio
async def test_create_subscription_stores_secret_only_in_vault() -> None:
    tenant_id = uuid4()

    repository = MagicMock(spec=OutgoingWebhookRepository)

    repository.tenant_id = tenant_id
    repository.flush = AsyncMock()

    repository.add_subscription.return_value = SimpleNamespace()

    audit_repository = MagicMock(spec=BusinessAuditLogRepository)

    vault = AsyncMock(spec=VaultClient)

    validator = AsyncMock(spec=WebhookEndpointValidator)

    validator.validate.return_value = "https://example.com/hooks"

    service = OutgoingWebhookSubscriptionService(
        repository=repository,
        audit_repository=(audit_repository),
        vault_client=vault,
        path_builder=(VaultPathBuilder()),
        endpoint_validator=validator,
    )

    await service.create(
        context=AuthorizationContext(
            actor_id="tenant-admin",
            role=Role.TENANT_ADMIN,
            tenant_id=tenant_id,
        ),
        name="ERP Hook",
        endpoint_url=("https://example.com/hooks"),
        event_types=[
            "message.received",
        ],
        signing_secret="s" * 32,
    )

    write_call = vault.write_secret.await_args

    path = write_call.kwargs["path"]

    assert path.startswith((f"whatsapp-platform/tenants/{tenant_id}/webhooks/"))

    assert write_call.kwargs["secret"] == {"signing_secret": "s" * 32}

    add_call = repository.add_subscription.call_args

    assert "signing_secret" not in add_call.kwargs

    assert add_call.kwargs["vault_secret_reference"] == path

    (audit_repository.add_outgoing_webhook_created.assert_called_once())

    audit_call = audit_repository.add_outgoing_webhook_created.call_args

    assert audit_call.kwargs["actor_id"] == "tenant-admin"

    assert audit_call.kwargs["name"] == "ERP Hook"

    assert audit_call.kwargs["event_types"] == [
        "message.received",
    ]

    assert "signing_secret" not in audit_call.kwargs


@pytest.mark.asyncio
async def test_unsupported_event_is_rejected_before_vault_write() -> None:
    tenant_id = uuid4()

    repository = MagicMock(spec=OutgoingWebhookRepository)

    repository.tenant_id = tenant_id

    audit_repository = MagicMock(spec=BusinessAuditLogRepository)

    vault = AsyncMock(spec=VaultClient)

    validator = AsyncMock(spec=WebhookEndpointValidator)

    service = OutgoingWebhookSubscriptionService(
        repository=repository,
        audit_repository=(audit_repository),
        vault_client=vault,
        path_builder=(VaultPathBuilder()),
        endpoint_validator=validator,
    )

    with pytest.raises(OutgoingWebhookSubscriptionInvalidError):
        await service.create(
            context=AuthorizationContext(
                actor_id="tenant-admin",
                role=Role.TENANT_ADMIN,
                tenant_id=tenant_id,
            ),
            name="Bad Hook",
            endpoint_url=("https://example.com"),
            event_types=["unknown.event"],
            signing_secret="s" * 32,
        )

    vault.write_secret.assert_not_awaited()

    (audit_repository.add_outgoing_webhook_created.assert_not_called())
