from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from app.db.models.message import (
    Message,
    MessageStatus,
    MessageType,
)
from app.db.models.template import (
    TemplateStatus,
)
from app.integrations.meta.client import (
    MetaCloudAPIAmbiguousResponseError,
    MetaCloudAPIClient,
    MetaCloudAPIPermanentError,
)
from app.integrations.meta.outbound_credentials import (
    MetaOutboundCredentialProvider,
    MetaOutboundCredentialsInvalidError,
)
from app.repositories.message_status import (
    MessageStatusRepository,
)
from app.repositories.meta_outbound import (
    MetaOutboundRepository,
)


class MetaOutboundProcessingError(RuntimeError):
    pass


class MetaOutboundMessageNotFoundError(MetaOutboundProcessingError):
    pass


class MetaOutboundAmbiguousDeliveryError(MetaOutboundProcessingError):
    """
    Delivery may already have happened
    at Meta.

    Do not automatically retry this
    condition.
    """


class MetaOutboundOutcome(StrEnum):
    SENT = "sent"
    ALREADY_FINAL = "already_final"
    PERMANENT_FAILURE = "permanent_failure"


@dataclass(frozen=True, slots=True)
class MetaOutboundResult:
    outcome: MetaOutboundOutcome
    message_id: UUID
    meta_message_id: str | None = None
    failure_code: str | None = None


class MetaOutboundSendService:
    def __init__(
        self,
        *,
        repository: MetaOutboundRepository,
        status_repository: (MessageStatusRepository),
        credential_provider: (MetaOutboundCredentialProvider),
        meta_client: MetaCloudAPIClient,
    ) -> None:
        self._repository = repository
        self._status_repository = status_repository
        self._credential_provider = credential_provider
        self._meta_client = meta_client

    async def send(
        self,
        *,
        message_id: UUID,
    ) -> MetaOutboundResult:
        message = await self._repository.lock_outbound_message(message_id)

        if message is None:
            raise (MetaOutboundMessageNotFoundError)

        if self._is_final(message):
            return MetaOutboundResult(
                outcome=(MetaOutboundOutcome.ALREADY_FINAL),
                message_id=message.id,
                meta_message_id=(message.meta_message_id),
            )

        if message.status is not MessageStatus.PENDING:
            return self._permanent_failure(
                message=message,
                failure_code=("INVALID_MESSAGE_STATUS"),
            )

        if message.message_type not in {
            MessageType.TEXT,
            MessageType.TEMPLATE,
        }:
            return self._permanent_failure(
                message=message,
                failure_code=("UNSUPPORTED_MESSAGE_TYPE"),
            )

        body_text: str | None = None

        if message.message_type is MessageType.TEXT:
            body_text = message.body_text

            if body_text is None or not body_text.strip():
                return self._permanent_failure(
                    message=message,
                    failure_code=("MESSAGE_BODY_MISSING"),
                )

        conversation = await self._repository.get_conversation(message.conversation_id)

        if conversation is None:
            return self._permanent_failure(
                message=message,
                failure_code=("CONVERSATION_NOT_FOUND"),
            )

        contact = await self._repository.get_active_contact(conversation.customer_contact_id)

        if contact is None:
            return self._permanent_failure(
                message=message,
                failure_code=("CUSTOMER_CONTACT_UNAVAILABLE"),
            )

        whatsapp_number = await self._repository.get_active_whatsapp_number(
            conversation.whatsapp_number_id
        )

        if whatsapp_number is None:
            return self._permanent_failure(
                message=message,
                failure_code=("WHATSAPP_NUMBER_UNAVAILABLE"),
            )

        integration = await self._repository.get_active_meta_integration(
            whatsapp_number.integration_id
        )

        if integration is None:
            return self._permanent_failure(
                message=message,
                failure_code=("META_INTEGRATION_UNAVAILABLE"),
            )

        graph_api_version = self._graph_api_version(integration.config_json)

        if graph_api_version is None:
            return self._permanent_failure(
                message=message,
                failure_code=("META_GRAPH_API_VERSION_MISSING"),
            )

        template_send: (
            tuple[
                str,
                str,
                list[dict[str, object]],
            ]
            | None
        ) = None

        if message.message_type is MessageType.TEMPLATE:
            template_payload = await self._repository.get_template_payload(message.id)

            if template_payload is None:
                return self._permanent_failure(
                    message=message,
                    failure_code=("TEMPLATE_PAYLOAD_MISSING"),
                )

            template = await self._repository.get_meta_template(template_payload.template_id)

            if template is None:
                return self._permanent_failure(
                    message=message,
                    failure_code=("META_TEMPLATE_NOT_FOUND"),
                )

            if template.status is not TemplateStatus.APPROVED:
                return self._permanent_failure(
                    message=message,
                    failure_code=("META_TEMPLATE_NOT_APPROVED"),
                )

            if template.meta_account_id != integration.id:
                return self._permanent_failure(
                    message=message,
                    failure_code=("META_TEMPLATE_ACCOUNT_MISMATCH"),
                )

            if template.meta_template_name is None or template.language is None:
                return self._permanent_failure(
                    message=message,
                    failure_code=("META_TEMPLATE_INVALID"),
                )

            template_send = (
                template.meta_template_name,
                template.language,
                list(template_payload.components_json),
            )

        try:
            credentials = await self._credential_provider.get_credentials(integration)

        except MetaOutboundCredentialsInvalidError:
            return self._permanent_failure(
                message=message,
                failure_code=("META_CREDENTIALS_INVALID"),
            )

        try:
            if message.message_type is MessageType.TEXT:
                if body_text is None:
                    raise RuntimeError(("Validated text message has no body."))

                result = await self._meta_client.send_text(
                    graph_api_version=(graph_api_version),
                    phone_number_id=(whatsapp_number.meta_phone_number_id),
                    recipient_phone=(contact.normalized_phone),
                    body_text=body_text,
                    access_token=(credentials.access_token),
                )

            else:
                if template_send is None:
                    raise RuntimeError(("Validated template message has no template payload."))

                (
                    template_name,
                    language,
                    components,
                ) = template_send

                result = await self._meta_client.send_template(
                    graph_api_version=(graph_api_version),
                    phone_number_id=(whatsapp_number.meta_phone_number_id),
                    recipient_phone=(contact.normalized_phone),
                    template_name=(template_name),
                    language=language,
                    components=components,
                    access_token=(credentials.access_token),
                )

        except MetaCloudAPIPermanentError:
            return self._permanent_failure(
                message=message,
                failure_code=("META_SEND_REJECTED"),
            )

        except MetaCloudAPIAmbiguousResponseError as exc:
            raise (
                MetaOutboundAmbiguousDeliveryError(("Meta delivery result is ambiguous."))
            ) from exc

        message.meta_message_id = result.meta_message_id

        self._status_repository.add_status_history(
            message_id=message.id,
            status=MessageStatus.SENT,
            meta_timestamp=None,
        )

        self._status_repository.set_effective_status(
            message=message,
            status=MessageStatus.SENT,
        )

        self._status_repository.add_status_outbox_event(
            message=message,
            status=MessageStatus.SENT,
        )

        return MetaOutboundResult(
            outcome=MetaOutboundOutcome.SENT,
            message_id=message.id,
            meta_message_id=(result.meta_message_id),
        )

    def _permanent_failure(
        self,
        *,
        message: Message,
        failure_code: str,
    ) -> MetaOutboundResult:
        self._status_repository.add_status_history(
            message_id=message.id,
            status=MessageStatus.FAILED,
            meta_timestamp=None,
        )

        self._status_repository.set_effective_status(
            message=message,
            status=MessageStatus.FAILED,
        )

        self._status_repository.add_status_outbox_event(
            message=message,
            status=MessageStatus.FAILED,
        )

        return MetaOutboundResult(
            outcome=(MetaOutboundOutcome.PERMANENT_FAILURE),
            message_id=message.id,
            meta_message_id=(message.meta_message_id),
            failure_code=failure_code,
        )

    @staticmethod
    def _is_final(
        message: Message,
    ) -> bool:
        return message.status in {
            MessageStatus.SENT,
            MessageStatus.DELIVERED,
            MessageStatus.READ,
            MessageStatus.FAILED,
        }

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
