from __future__ import annotations

import hashlib
import hmac
import json
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.db.models.integration import (
    Integration,
    IntegrationProvider,
)
from app.db.models.raw_webhook_event import (
    RawWebhookProcessingStatus,
)
from app.db.models.whatsapp_number import (
    WhatsAppNumber,
)
from app.integrations.meta.webhook_security import (
    MetaWebhookCredentialProvider,
    MetaWebhookCredentials,
)
from app.repositories.meta_webhook import (
    MetaWebhookRepository,
)
from app.services.meta_webhook import (
    MetaWebhookIngressService,
    MetaWebhookInvalidSignatureError,
    MetaWebhookVerificationError,
)


def _integration() -> Integration:
    return Integration(
        id=uuid4(),
        tenant_id=uuid4(),
        provider=IntegrationProvider.META,
        name="Meta",
        active=True,
    )


def _payload(
    phone_number_id: str,
) -> dict[str, object]:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "waba-1",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "metadata": {
                                "phone_number_id": (phone_number_id),
                                "display_phone_number": ("15551234567"),
                            },
                            "messages": [
                                {
                                    "id": "wamid.1",
                                    "from": "201234567890",
                                    "type": "text",
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }


def _signed_body(
    payload: dict[str, object],
) -> tuple[bytes, str]:
    raw_body = json.dumps(
        payload,
        separators=(",", ":"),
    ).encode()

    digest = hmac.new(
        b"app-secret",
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    return (
        raw_body,
        f"sha256={digest}",
    )


def _service(
    integration: Integration,
):
    repository = AsyncMock(
        spec=MetaWebhookRepository,
    )

    credentials = AsyncMock(
        spec=MetaWebhookCredentialProvider,
    )

    repository.get_active_meta_integration.return_value = integration

    credentials.get_credentials.return_value = MetaWebhookCredentials(
        verify_token="verify-token",
        app_secret="app-secret",
    )

    service = MetaWebhookIngressService(
        repository=repository,
        credential_provider=credentials,
    )

    return (
        service,
        repository,
    )


@pytest.mark.asyncio
async def test_verification_returns_challenge() -> None:
    integration = _integration()

    service, _ = _service(integration)

    result = await service.verify_challenge(
        integration_id=integration.id,
        mode="subscribe",
        verify_token="verify-token",
        challenge="123456",
    )

    assert result == "123456"


@pytest.mark.asyncio
async def test_wrong_verify_token_is_rejected() -> None:
    integration = _integration()

    service, _ = _service(integration)

    with pytest.raises(MetaWebhookVerificationError):
        await service.verify_challenge(
            integration_id=integration.id,
            mode="subscribe",
            verify_token="wrong",
            challenge="123456",
        )


@pytest.mark.asyncio
async def test_valid_webhook_creates_raw_event_and_outbox() -> None:
    integration = _integration()
    phone_number_id = "123456789"
    raw_event_id = uuid4()

    service, repository = _service(integration)

    repository.get_active_whatsapp_numbers.return_value = [
        WhatsAppNumber(
            id=uuid4(),
            tenant_id=integration.tenant_id,
            integration_id=integration.id,
            meta_phone_number_id=(phone_number_id),
            display_phone_number=("+15551234567"),
            active=True,
        )
    ]

    repository.insert_raw_event_if_new.return_value = raw_event_id

    payload = _payload(phone_number_id)

    raw_body, signature = _signed_body(payload)

    result = await service.receive(
        integration_id=integration.id,
        raw_body=raw_body,
        signature_header=signature,
    )

    assert result.raw_event_id == raw_event_id
    assert result.duplicate is False
    assert result.tenant_resolved is True

    repository.insert_raw_event_if_new.assert_awaited_once()

    call = repository.insert_raw_event_if_new.await_args

    assert call.kwargs["tenant_id"] == integration.tenant_id

    assert call.kwargs["processing_status"] is RawWebhookProcessingStatus.RECEIVED

    repository.add_inbound_outbox_event.assert_called_once_with(
        tenant_id=integration.tenant_id,
        raw_event_id=raw_event_id,
    )


@pytest.mark.asyncio
async def test_duplicate_does_not_create_second_outbox() -> None:
    integration = _integration()
    phone_number_id = "123456789"

    service, repository = _service(integration)

    repository.get_active_whatsapp_numbers.return_value = [
        WhatsAppNumber(
            id=uuid4(),
            tenant_id=integration.tenant_id,
            integration_id=integration.id,
            meta_phone_number_id=(phone_number_id),
            display_phone_number=("+15551234567"),
            active=True,
        )
    ]

    repository.insert_raw_event_if_new.return_value = None

    raw_body, signature = _signed_body(_payload(phone_number_id))

    result = await service.receive(
        integration_id=integration.id,
        raw_body=raw_body,
        signature_header=signature,
    )

    assert result.duplicate is True

    repository.add_inbound_outbox_event.assert_not_called()


@pytest.mark.asyncio
async def test_unknown_phone_number_is_persisted_unresolved() -> None:
    integration = _integration()

    service, repository = _service(integration)

    repository.get_active_whatsapp_numbers.return_value = []

    repository.insert_raw_event_if_new.return_value = uuid4()

    raw_body, signature = _signed_body(_payload("unknown-phone"))

    result = await service.receive(
        integration_id=integration.id,
        raw_body=raw_body,
        signature_header=signature,
    )

    assert result.tenant_resolved is False

    call = repository.insert_raw_event_if_new.await_args

    assert call.kwargs["tenant_id"] is None

    assert call.kwargs["processing_status"] is RawWebhookProcessingStatus.UNRESOLVED

    assert call.kwargs["last_error"] == "META_PHONE_NUMBER_ID_UNKNOWN"

    repository.add_inbound_outbox_event.assert_not_called()


@pytest.mark.asyncio
async def test_invalid_signature_writes_nothing() -> None:
    integration = _integration()

    service, repository = _service(integration)

    with pytest.raises(MetaWebhookInvalidSignatureError):
        await service.receive(
            integration_id=integration.id,
            raw_body=b'{"test":true}',
            signature_header=("sha256=" + ("0" * 64)),
        )

    repository.insert_raw_event_if_new.assert_not_awaited()
    repository.add_inbound_outbox_event.assert_not_called()
