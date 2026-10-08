from __future__ import annotations

from unittest.mock import (
    AsyncMock,
    MagicMock,
)
from uuid import uuid4

import pytest

from app.db.models.conversation import (
    Conversation,
    ConversationState,
)
from app.db.models.customer_contact import (
    CustomerContact,
)
from app.db.models.integration import (
    Integration,
    IntegrationProvider,
)
from app.db.models.message import (
    Message,
    MessageDirection,
    MessageStatus,
    MessageType,
)
from app.db.models.whatsapp_number import (
    WhatsAppNumber,
)
from app.integrations.meta.client import (
    MetaCloudAPIClient,
    MetaCloudAPIRetryableError,
    MetaSendMessageResult,
)
from app.integrations.meta.outbound_credentials import (
    MetaOutboundCredentialProvider,
    MetaOutboundCredentials,
)
from app.repositories.message_status import (
    MessageStatusRepository,
)
from app.repositories.meta_outbound import (
    MetaOutboundRepository,
)
from app.services.meta_outbound import (
    MetaOutboundOutcome,
    MetaOutboundSendService,
)


def _objects():
    tenant_id = uuid4()

    message = Message(
        id=uuid4(),
        tenant_id=tenant_id,
        conversation_id=uuid4(),
        direction=(MessageDirection.OUTBOUND),
        message_type=MessageType.TEXT,
        body_text="Hello",
        status=MessageStatus.PENDING,
    )

    conversation = Conversation(
        id=message.conversation_id,
        tenant_id=tenant_id,
        whatsapp_number_id=uuid4(),
        customer_contact_id=uuid4(),
        group_id=uuid4(),
        state=ConversationState.CLAIMED,
    )

    contact = CustomerContact(
        id=conversation.customer_contact_id,
        tenant_id=tenant_id,
        customer_company_id=uuid4(),
        phone_number="+201000000000",
        normalized_phone="201000000000",
        active=True,
    )

    integration = Integration(
        id=uuid4(),
        tenant_id=tenant_id,
        provider=IntegrationProvider.META,
        name="Meta Main",
        config_json={
            "graph_api_version": "v99.0",
        },
        vault_secret_reference=("whatsapp-platform/tenants/test/meta/main"),
        active=True,
    )

    number = WhatsAppNumber(
        id=conversation.whatsapp_number_id,
        tenant_id=tenant_id,
        integration_id=integration.id,
        meta_phone_number_id="123456",
        display_phone_number=("+201111111111"),
        active=True,
    )

    return (
        message,
        conversation,
        contact,
        number,
        integration,
    )


@pytest.mark.asyncio
async def test_success_marks_message_sent() -> None:
    (
        message,
        conversation,
        contact,
        number,
        integration,
    ) = _objects()

    repository = AsyncMock(spec=MetaOutboundRepository)

    status_repository = MagicMock(spec=MessageStatusRepository)

    credential_provider = AsyncMock(spec=MetaOutboundCredentialProvider)

    meta_client = AsyncMock(spec=MetaCloudAPIClient)

    repository.lock_outbound_message.return_value = message
    repository.get_conversation.return_value = conversation
    repository.get_active_contact.return_value = contact
    repository.get_active_whatsapp_number.return_value = number
    repository.get_active_meta_integration.return_value = integration

    credential_provider.get_credentials.return_value = MetaOutboundCredentials(
        access_token="secret-token"
    )

    meta_client.send_text.return_value = MetaSendMessageResult(meta_message_id="wamid.123")

    service = MetaOutboundSendService(
        repository=repository,
        status_repository=(status_repository),
        credential_provider=(credential_provider),
        meta_client=meta_client,
    )

    result = await service.send(message_id=message.id)

    assert result.outcome is MetaOutboundOutcome.SENT

    assert message.meta_message_id == "wamid.123"

    status_repository.add_status_history.assert_called_once_with(
        message_id=message.id,
        status=MessageStatus.SENT,
        meta_timestamp=None,
    )

    status_repository.set_effective_status.assert_called_once_with(
        message=message,
        status=MessageStatus.SENT,
    )

    status_repository.add_status_outbox_event.assert_called_once_with(
        message=message,
        status=MessageStatus.SENT,
    )


@pytest.mark.asyncio
async def test_already_sent_does_not_call_meta() -> None:
    (
        message,
        _,
        _,
        _,
        _,
    ) = _objects()

    message.status = MessageStatus.SENT
    message.meta_message_id = "wamid.old"

    repository = AsyncMock(spec=MetaOutboundRepository)
    repository.lock_outbound_message.return_value = message

    status_repository = MagicMock(spec=MessageStatusRepository)

    credential_provider = AsyncMock(spec=MetaOutboundCredentialProvider)

    meta_client = AsyncMock(spec=MetaCloudAPIClient)

    service = MetaOutboundSendService(
        repository=repository,
        status_repository=(status_repository),
        credential_provider=(credential_provider),
        meta_client=meta_client,
    )

    result = await service.send(message_id=message.id)

    assert result.outcome is MetaOutboundOutcome.ALREADY_FINAL

    meta_client.send_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_retryable_meta_error_keeps_pending() -> None:
    (
        message,
        conversation,
        contact,
        number,
        integration,
    ) = _objects()

    repository = AsyncMock(spec=MetaOutboundRepository)

    repository.lock_outbound_message.return_value = message
    repository.get_conversation.return_value = conversation
    repository.get_active_contact.return_value = contact
    repository.get_active_whatsapp_number.return_value = number
    repository.get_active_meta_integration.return_value = integration

    status_repository = MagicMock(spec=MessageStatusRepository)

    credential_provider = AsyncMock(spec=MetaOutboundCredentialProvider)

    credential_provider.get_credentials.return_value = MetaOutboundCredentials(
        access_token="secret-token"
    )

    meta_client = AsyncMock(spec=MetaCloudAPIClient)

    meta_client.send_text.side_effect = MetaCloudAPIRetryableError("temporary")

    service = MetaOutboundSendService(
        repository=repository,
        status_repository=(status_repository),
        credential_provider=(credential_provider),
        meta_client=meta_client,
    )

    with pytest.raises(MetaCloudAPIRetryableError):
        await service.send(message_id=message.id)

    assert message.status is MessageStatus.PENDING

    status_repository.set_effective_status.assert_not_called()
