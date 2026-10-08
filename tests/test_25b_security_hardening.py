from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest

from app.auth.config import (
    AuthConfigurationError,
    load_auth_login_config,
    load_session_cookie_config,
)
from app.integrations.meta.media_client import (
    MetaDownloadedMedia,
    MetaMediaAPIClient,
    MetaMediaAPIPermanentError,
)
from app.media_security import (
    MediaSecurityConfigurationError,
    MediaSecurityPolicy,
    load_media_security_policy,
)
from app.services.meta_media import (
    MetaMediaPermanentProcessingError,
    MetaMediaProcessingService,
)


def _set_login_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "KEYCLOAK_PUBLIC_URL",
        "https://identity.example.com",
    )
    monkeypatch.setenv(
        "KEYCLOAK_REALM",
        "whatsapp-platform",
    )
    monkeypatch.setenv(
        "KEYCLOAK_BFF_CLIENT_ID",
        "whatsapp-platform-bff",
    )
    monkeypatch.setenv(
        "AUTH_REDIRECT_URI",
        ("https://app.example.com/auth/callback"),
    )


def test_production_session_cookie_defaults_secure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "APP_ENV",
        "production",
    )
    monkeypatch.delenv(
        "AUTH_SESSION_COOKIE_SECURE",
        raising=False,
    )

    config = load_session_cookie_config()

    assert config.secure is True


def test_production_rejects_insecure_session_cookie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "APP_ENV",
        "production",
    )
    monkeypatch.setenv(
        "AUTH_SESSION_COOKIE_SECURE",
        "false",
    )

    with pytest.raises(AuthConfigurationError):
        load_session_cookie_config()


def test_production_rejects_insecure_transaction_cookie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_login_env(monkeypatch)

    monkeypatch.setenv(
        "APP_ENV",
        "production",
    )
    monkeypatch.setenv(
        "AUTH_TRANSACTION_COOKIE_SECURE",
        "false",
    )

    with pytest.raises(AuthConfigurationError):
        load_auth_login_config()


def test_production_rejects_http_public_keycloak(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_login_env(monkeypatch)

    monkeypatch.setenv(
        "APP_ENV",
        "production",
    )
    monkeypatch.setenv(
        "KEYCLOAK_PUBLIC_URL",
        "http://identity.example.com",
    )

    with pytest.raises(AuthConfigurationError):
        load_auth_login_config()


def test_media_security_policy_reads_size_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    load_media_security_policy.cache_clear()

    monkeypatch.setenv(
        "MEDIA_MAX_SIZE_BYTES",
        "12345",
    )

    policy = load_media_security_policy()

    assert policy.max_size_bytes == 12345

    load_media_security_policy.cache_clear()


def test_media_security_policy_rejects_invalid_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    load_media_security_policy.cache_clear()

    monkeypatch.setenv(
        "MEDIA_MAX_SIZE_BYTES",
        "0",
    )

    with pytest.raises(MediaSecurityConfigurationError):
        load_media_security_policy()

    load_media_security_policy.cache_clear()


@pytest.mark.asyncio
async def test_meta_client_rejects_provider_size_before_download() -> None:
    requests: list[str] = []

    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        requests.append(str(request.url))

        return httpx.Response(
            status_code=200,
            json={
                "id": "media-123",
                "url": ("https://cdn.example.com/media"),
                "mime_type": ("application/pdf"),
                "file_size": "11",
            },
        )

    transport = httpx.MockTransport(handler)

    async with httpx.AsyncClient(transport=transport) as http_client:
        client = MetaMediaAPIClient(http_client)

        with pytest.raises(MetaMediaAPIPermanentError):
            await client.download_media(
                graph_api_version="v23.0",
                provider_media_id=("media-123"),
                phone_number_id=("phone-123"),
                access_token="secret",
                max_size_bytes=10,
            )

    assert len(requests) == 1


def _media_service(
    *,
    downloaded: MetaDownloadedMedia,
    policy: MediaSecurityPolicy,
) -> tuple[
    MetaMediaProcessingService,
    AsyncMock,
]:
    repository = AsyncMock()
    media_repository = AsyncMock()
    credential_provider = AsyncMock()
    meta_client = AsyncMock()
    upload_service = AsyncMock()

    message_id = uuid4()

    media_repository.get_by_message.return_value = None

    repository.get_inbound_media_message.return_value = SimpleNamespace(
        id=message_id,
        conversation_id=uuid4(),
    )

    repository.get_conversation.return_value = SimpleNamespace(
        whatsapp_number_id=uuid4(),
    )

    repository.get_whatsapp_number.return_value = SimpleNamespace(
        integration_id=uuid4(),
        meta_phone_number_id=("phone-123"),
    )

    repository.get_meta_integration.return_value = SimpleNamespace(
        config_json={
            "graph_api_version": "v23.0",
        }
    )

    credential_provider.get_credentials.return_value = SimpleNamespace(
        access_token="secret",
    )

    meta_client.download_media.return_value = downloaded

    upload_service.upload_bytes.return_value = SimpleNamespace(
        id=uuid4(),
    )

    service = MetaMediaProcessingService(
        repository=repository,
        media_repository=media_repository,
        credential_provider=(credential_provider),
        meta_client=meta_client,
        upload_service=upload_service,
        security_policy=policy,
    )

    return (
        service,
        upload_service,
    )


@pytest.mark.asyncio
async def test_media_service_rejects_disallowed_mime_before_s3() -> None:
    message_id = uuid4()

    repository = AsyncMock()
    media_repository = AsyncMock()
    credential_provider = AsyncMock()
    meta_client = AsyncMock()
    upload_service = AsyncMock()

    media_repository.get_by_message.return_value = None

    repository.get_inbound_media_message.return_value = SimpleNamespace(
        id=message_id,
        conversation_id=uuid4(),
    )

    repository.get_conversation.return_value = SimpleNamespace(
        whatsapp_number_id=uuid4(),
    )

    repository.get_whatsapp_number.return_value = SimpleNamespace(
        integration_id=uuid4(),
        meta_phone_number_id="phone-123",
    )

    repository.get_meta_integration.return_value = SimpleNamespace(
        config_json={
            "graph_api_version": "v23.0",
        }
    )

    credential_provider.get_credentials.return_value = SimpleNamespace(
        access_token="secret",
    )

    meta_client.download_media.return_value = MetaDownloadedMedia(
        data=b"abc",
        mime_type=("application/x-msdownload"),
        provider_sha256=None,
        provider_size_bytes=3,
    )

    service = MetaMediaProcessingService(
        repository=repository,
        media_repository=media_repository,
        credential_provider=credential_provider,
        meta_client=meta_client,
        upload_service=upload_service,
        security_policy=MediaSecurityPolicy(
            max_size_bytes=100,
            allowed_mime_types=frozenset(
                {
                    "application/pdf",
                }
            ),
        ),
    )

    with pytest.raises(MetaMediaPermanentProcessingError):
        await service.process(
            message_id=message_id,
            provider_media_id="media-123",
            original_filename="payload.exe",
            webhook_mime_type=None,
        )

    upload_service.upload_bytes.assert_not_awaited()
