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
from app.db.models.message_template_payload import (
    MessageTemplatePayload,
)
from app.db.models.template import (
    Template,
    TemplateStatus,
    TemplateType,
)
from app.db.models.whatsapp_number import (
    WhatsAppNumber,
)
from app.integrations.meta.client import (
    MetaCloudAPIClient,
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
        direction=MessageDirection.OUTBOUND,
        message_type=MessageType.TEMPLATE,
        body_text=None,
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
        vault_secret_reference=(f"whatsapp-platform/tenants/{tenant_id}/meta/main"),
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
        components_json=[],
        status=TemplateStatus.APPROVED,
        meta_account_id=integration.id,
        last_synced_at=None,
    )

    payload = MessageTemplatePayload(
        id=uuid4(),
        tenant_id=tenant_id,
        message_id=message.id,
        template_id=template.id,
        components_json=[
            {
                "type": "body",
                "parameters": [
                    {
                        "type": "text",
                        "text": "Ahmed",
                    }
                ],
            }
        ],
    )

    return (
        message,
        conversation,
        contact,
        number,
        integration,
        template,
        payload,
    )


@pytest.mark.asyncio
async def test_template_success_marks_message_sent() -> None:
    (
        message,
        conversation,
        contact,
        number,
        integration,
        template,
        payload,
    ) = _objects()

    repository = AsyncMock(spec=MetaOutboundRepository)

    status_repository = MagicMock(spec=MessageStatusRepository)

    credentials = AsyncMock(spec=MetaOutboundCredentialProvider)

    meta_client = AsyncMock(spec=MetaCloudAPIClient)

    repository.lock_outbound_message.return_value = message
    repository.get_conversation.return_value = conversation
    repository.get_active_contact.return_value = contact
    repository.get_active_whatsapp_number.return_value = number
    repository.get_active_meta_integration.return_value = integration
    repository.get_template_payload.return_value = payload
    repository.get_meta_template.return_value = template

    credentials.get_credentials.return_value = MetaOutboundCredentials(access_token="secret-token")

    meta_client.send_template.return_value = MetaSendMessageResult(
        meta_message_id=("wamid.template-123")
    )

    service = MetaOutboundSendService(
        repository=repository,
        status_repository=(status_repository),
        credential_provider=credentials,
        meta_client=meta_client,
    )

    result = await service.send(message_id=message.id)

    assert result.outcome is MetaOutboundOutcome.SENT

    assert message.meta_message_id == "wamid.template-123"

    meta_client.send_template.assert_awaited_once_with(
        graph_api_version="v99.0",
        phone_number_id="123456",
        recipient_phone="201000000000",
        template_name=("payment_reminder"),
        language="en_US",
        components=payload.components_json,
        access_token="secret-token",
    )


@pytest.mark.asyncio
async def test_template_no_longer_approved_fails_before_meta() -> None:
    (
        message,
        conversation,
        contact,
        number,
        integration,
        template,
        payload,
    ) = _objects()

    template.status = TemplateStatus.PAUSED

    repository = AsyncMock(spec=MetaOutboundRepository)

    repository.lock_outbound_message.return_value = message
    repository.get_conversation.return_value = conversation
    repository.get_active_contact.return_value = contact
    repository.get_active_whatsapp_number.return_value = number
    repository.get_active_meta_integration.return_value = integration
    repository.get_template_payload.return_value = payload
    repository.get_meta_template.return_value = template

    status_repository = MagicMock(spec=MessageStatusRepository)

    credentials = AsyncMock(spec=MetaOutboundCredentialProvider)

    meta_client = AsyncMock(spec=MetaCloudAPIClient)

    service = MetaOutboundSendService(
        repository=repository,
        status_repository=(status_repository),
        credential_provider=credentials,
        meta_client=meta_client,
    )

    result = await service.send(message_id=message.id)

    assert result.outcome is MetaOutboundOutcome.PERMANENT_FAILURE

    assert result.failure_code == "META_TEMPLATE_NOT_APPROVED"

    meta_client.send_template.assert_not_awaited()
    credentials.get_credentials.assert_not_awaited()
