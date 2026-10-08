from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID, uuid5

from app.integrations.meta.media_client import (
    MetaMediaAPIClient,
    MetaMediaAPIPermanentError,
)
from app.integrations.meta.outbound_credentials import (
    MetaOutboundCredentialProvider,
    MetaOutboundCredentialsInvalidError,
)
from app.media_security import (
    MediaSecurityError,
    MediaSecurityPolicy,
    load_media_security_policy,
    validate_media_metadata,
)
from app.repositories.media import (
    MediaRepository,
)
from app.repositories.meta_media import (
    MetaMediaRepository,
)
from app.services.media_upload import (
    MediaMessageNotFoundError,
    MediaUploadInvalidError,
    MediaUploadService,
)


class MetaMediaProcessingError(RuntimeError):
    pass


class MetaMediaPermanentProcessingError(MetaMediaProcessingError):
    pass


class MetaMediaProcessOutcome(StrEnum):
    PROCESSED = "processed"
    ALREADY_PROCESSED = "already_processed"


@dataclass(
    frozen=True,
    slots=True,
)
class MetaMediaProcessResult:
    outcome: MetaMediaProcessOutcome
    message_id: UUID
    media_id: UUID | None = None


class MetaMediaProcessingService:
    def __init__(
        self,
        *,
        repository: MetaMediaRepository,
        media_repository: MediaRepository,
        credential_provider: (MetaOutboundCredentialProvider),
        meta_client: MetaMediaAPIClient,
        upload_service: MediaUploadService,
        security_policy: (MediaSecurityPolicy | None) = None,
    ) -> None:
        self._repository = repository
        self._media_repository = media_repository
        self._credential_provider = credential_provider
        self._meta_client = meta_client
        self._upload_service = upload_service

        self._security_policy = security_policy or load_media_security_policy()

    async def process(
        self,
        *,
        message_id: UUID,
        provider_media_id: str,
        original_filename: str | None,
        webhook_mime_type: str | None,
    ) -> MetaMediaProcessResult:
        existing = await self._media_repository.get_by_message(message_id)

        if existing is not None:
            return MetaMediaProcessResult(
                outcome=(MetaMediaProcessOutcome.ALREADY_PROCESSED),
                message_id=message_id,
                media_id=existing.id,
            )

        message = await self._repository.get_inbound_media_message(message_id)

        if message is None:
            raise (MetaMediaPermanentProcessingError("Inbound media message was not found."))

        conversation = await self._repository.get_conversation(message.conversation_id)

        if conversation is None:
            raise (MetaMediaPermanentProcessingError("Media conversation was not found."))

        whatsapp_number = await self._repository.get_whatsapp_number(
            conversation.whatsapp_number_id
        )

        if whatsapp_number is None:
            raise (MetaMediaPermanentProcessingError("WhatsApp number was not found."))

        integration = await self._repository.get_meta_integration(whatsapp_number.integration_id)

        if integration is None:
            raise (MetaMediaPermanentProcessingError("Meta integration was not found."))

        graph_api_version = self._graph_api_version(integration.config_json)

        if graph_api_version is None:
            raise (MetaMediaPermanentProcessingError("Meta Graph API version is missing."))

        try:
            credentials = await self._credential_provider.get_credentials(integration)
        except MetaOutboundCredentialsInvalidError as exc:
            raise (MetaMediaPermanentProcessingError("Meta credentials are invalid.")) from exc

        try:
            downloaded = await self._meta_client.download_media(
                graph_api_version=(graph_api_version),
                provider_media_id=(provider_media_id),
                phone_number_id=(whatsapp_number.meta_phone_number_id),
                access_token=(credentials.access_token),
                max_size_bytes=(self._security_policy.max_size_bytes),
            )

        except MetaMediaAPIPermanentError as exc:
            raise (
                MetaMediaPermanentProcessingError("Meta permanently rejected media retrieval.")
            ) from exc

        mime_type = downloaded.mime_type or self._normalize_mime_type(webhook_mime_type)

        if mime_type is None:
            raise (MetaMediaPermanentProcessingError("Media MIME type could not be resolved."))

        try:
            validated = validate_media_metadata(
                original_filename=(original_filename),
                mime_type=mime_type,
                size_bytes=len(downloaded.data),
                policy=(self._security_policy),
            )
        except MediaSecurityError as exc:
            raise (
                MetaMediaPermanentProcessingError(f"Media rejected by security policy: {exc.code}")
            ) from exc

        deterministic_media_id = uuid5(
            message.id,
            provider_media_id,
        )

        try:
            media = await self._upload_service.upload_bytes(
                message_id=message.id,
                data=downloaded.data,
                mime_type=(validated.mime_type),
                original_filename=(validated.original_filename),
                media_id=(deterministic_media_id),
                cleanup_on_persistence_failure=(False),
            )

        except (
            MediaMessageNotFoundError,
            MediaUploadInvalidError,
        ) as exc:
            raise (
                MetaMediaPermanentProcessingError("Media metadata is not valid for persistence.")
            ) from exc

        return MetaMediaProcessResult(
            outcome=(MetaMediaProcessOutcome.PROCESSED),
            message_id=message.id,
            media_id=media.id,
        )

    @staticmethod
    def _graph_api_version(
        config: dict[str, object],
    ) -> str | None:
        raw_value = config.get("graph_api_version")

        if (
            not isinstance(
                raw_value,
                str,
            )
            or not raw_value.strip()
        ):
            return None

        return raw_value.strip()

    @staticmethod
    def _normalize_mime_type(
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        normalized = value.strip()

        return normalized or None
