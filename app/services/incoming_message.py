from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from app.db.models.conversation import (
    Conversation,
    ConversationState,
)
from app.db.models.raw_webhook_event import (
    RawWebhookEvent,
)
from app.integrations.meta.message_echo_parser import (
    MetaMessageEchoPayloadError,
    ParsedMetaMessageEcho,
    UnsupportedMetaMessageEchoTypeError,
    parse_meta_message_echoes,
)
from app.integrations.meta.message_parser import (
    ParsedMetaInboundMedia,
    ParsedMetaInboundMessage,
    parse_meta_inbound_messages,
)
from app.repositories.incoming_message import (
    IncomingMessageRepository,
)


class IncomingMessageError(RuntimeError):
    pass


class IncomingMessageUnresolvedError(IncomingMessageError):
    def __init__(
        self,
        code: str,
    ) -> None:
        super().__init__(code)
        self.code = code


class IncomingMessageOutcome(StrEnum):
    PROCESSED = "processed"
    ALREADY_PROCESSED = "already_processed"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True, slots=True)
class IncomingMessageProcessResult:
    outcome: IncomingMessageOutcome
    created_message_count: int = 0
    created_conversation_count: int = 0


class CustomerCompanyResolver(Protocol):
    async def resolve_company_id(
        self,
        *,
        tenant_id: UUID,
        normalized_phone: str,
        display_name: str | None,
    ) -> UUID | None: ...


class OwnerUnavailabilityHandler(Protocol):
    async def handle_new_customer_work(
        self,
        *,
        conversation_id: UUID,
    ) -> object: ...


class IncomingMessageProcessor:
    def __init__(
        self,
        *,
        repository: IncomingMessageRepository,
        customer_company_resolver: CustomerCompanyResolver,
        owner_unavailability_handler: OwnerUnavailabilityHandler,
    ) -> None:
        self._repository = repository
        self._customer_company_resolver = customer_company_resolver
        self._owner_unavailability_handler = owner_unavailability_handler

    async def process_raw_event(
        self,
        raw_event: RawWebhookEvent,
    ) -> IncomingMessageProcessResult:
        if raw_event.tenant_id is None:
            raise IncomingMessageUnresolvedError("RAW_EVENT_TENANT_UNRESOLVED")

        if raw_event.tenant_id != self._repository.tenant_id:
            raise IncomingMessageUnresolvedError("RAW_EVENT_TENANT_MISMATCH")

        messages = parse_meta_inbound_messages(raw_event.payload_json)

        try:
            message_echoes = parse_meta_message_echoes(raw_event.payload_json)
        except UnsupportedMetaMessageEchoTypeError as exc:
            raise IncomingMessageUnresolvedError("META_MESSAGE_ECHO_TYPE_UNSUPPORTED") from exc
        except MetaMessageEchoPayloadError as exc:
            raise IncomingMessageUnresolvedError("META_MESSAGE_ECHO_PAYLOAD_INVALID") from exc

        if not messages and not message_echoes:
            return IncomingMessageProcessResult(outcome=IncomingMessageOutcome.NOT_APPLICABLE)

        created_messages = 0
        created_conversations = 0

        for parsed in messages:
            result = await self._process_message(parsed)

            if result[0]:
                created_messages += 1

            if result[1]:
                created_conversations += 1

        for parsed_echo in message_echoes:
            created = await self._process_external_message_echo(parsed_echo)

            if created:
                created_messages += 1

        return IncomingMessageProcessResult(
            outcome=IncomingMessageOutcome.PROCESSED,
            created_message_count=created_messages,
            created_conversation_count=(created_conversations),
        )

    async def _process_message(
        self,
        parsed: ParsedMetaInboundMessage,
    ) -> tuple[bool, bool]:
        whatsapp_number = await self._repository.get_active_whatsapp_number(
            parsed.meta_phone_number_id
        )

        if whatsapp_number is None:
            raise IncomingMessageUnresolvedError("WHATSAPP_NUMBER_NOT_FOUND")

        contact = await self._repository.get_contact_by_normalized_phone(
            parsed.normalized_sender_phone
        )

        if contact is None:
            company_id = await self._customer_company_resolver.resolve_company_id(
                tenant_id=self._repository.tenant_id,
                normalized_phone=(parsed.normalized_sender_phone),
                display_name=parsed.display_name,
            )

            if company_id is None:
                raise IncomingMessageUnresolvedError("CUSTOMER_COMPANY_RESOLUTION_REQUIRED")

            if not (await self._repository.customer_company_is_active(company_id)):
                raise IncomingMessageUnresolvedError("CUSTOMER_COMPANY_NOT_FOUND")

            contact = await self._repository.get_or_create_contact(
                customer_company_id=company_id,
                display_name=parsed.display_name,
                phone_number=parsed.sender_phone,
                normalized_phone=(parsed.normalized_sender_phone),
            )

        conversation = await self._repository.get_conversation(
            whatsapp_number_id=whatsapp_number.id,
            customer_contact_id=contact.id,
        )

        conversation_created = False

        if conversation is None:
            group_id = await self._resolve_group(whatsapp_number.id)

            (
                conversation,
                conversation_created,
            ) = await self._repository.get_or_create_conversation(
                whatsapp_number_id=whatsapp_number.id,
                customer_contact_id=contact.id,
                group_id=group_id,
            )

        elif conversation.group_id is None:
            group_id = await self._resolve_group(whatsapp_number.id)

            conversation = await self._repository.assign_group_if_missing(
                conversation_id=conversation.id,
                group_id=group_id,
            )

            if conversation.group_id != group_id:
                raise IncomingMessageUnresolvedError("CONVERSATION_GROUP_CONFLICT")

        (
            conversation,
            reopened,
        ) = await self._reopen_if_required(conversation)

        message_id = await self._repository.insert_message_if_new(
            conversation_id=conversation.id,
            meta_message_id=parsed.meta_message_id,
            message_type=parsed.message_type,
            body_text=parsed.body_text,
            external_actor_id=(parsed.normalized_sender_phone),
            meta_timestamp=parsed.meta_timestamp,
        )

        if message_id is None:
            return (
                False,
                conversation_created,
            )

        if conversation_created:
            await self._notify_new_queue(conversation)

        if reopened:
            self._repository.add_outbox_event(
                event_type="conversation.reopened",
                aggregate_type="conversation",
                aggregate_id=str(conversation.id),
                payload_json={
                    "conversation_id": str(conversation.id),
                    "group_id": (
                        str(conversation.group_id) if conversation.group_id is not None else None
                    ),
                },
            )

        self._repository.add_outbox_event(
            event_type="message.received",
            aggregate_type="message",
            aggregate_id=str(message_id),
            payload_json={
                "message_id": str(message_id),
                "conversation_id": str(conversation.id),
                "group_id": (
                    str(conversation.group_id) if conversation.group_id is not None else None
                ),
                "customer_contact_id": str(contact.id),
            },
        )

        if parsed.media is not None:
            self._queue_media_processing(
                message_id=message_id,
                media=parsed.media,
            )

        if conversation.responsible_employee_id is not None:
            await self._owner_unavailability_handler.handle_new_customer_work(
                conversation_id=conversation.id
            )

        return (
            True,
            conversation_created,
        )

    async def _process_external_message_echo(
        self,
        parsed: ParsedMetaMessageEcho,
    ) -> bool:
        whatsapp_number = await self._repository.get_active_whatsapp_number(
            parsed.meta_phone_number_id
        )

        if whatsapp_number is None:
            raise IncomingMessageUnresolvedError("WHATSAPP_NUMBER_NOT_FOUND")

        contact = await self._repository.get_contact_by_normalized_phone(
            parsed.normalized_recipient_phone
        )

        if contact is None:
            raise IncomingMessageUnresolvedError("EXTERNAL_MESSAGE_CUSTOMER_CONTACT_NOT_FOUND")

        conversation = await self._repository.get_conversation(
            whatsapp_number_id=whatsapp_number.id,
            customer_contact_id=contact.id,
        )

        if conversation is None:
            raise IncomingMessageUnresolvedError("EXTERNAL_MESSAGE_CONVERSATION_NOT_FOUND")

        message_id = await self._repository.insert_external_message_if_new(
            conversation_id=conversation.id,
            meta_message_id=parsed.meta_message_id,
            message_type=parsed.message_type,
            body_text=parsed.body_text,
            meta_timestamp=parsed.meta_timestamp,
        )

        if message_id is None:
            return False

        self._repository.add_outbox_event(
            event_type="message.sent",
            aggregate_type="message",
            aggregate_id=str(message_id),
            payload_json={
                "message_id": str(message_id),
                "conversation_id": str(conversation.id),
                "group_id": (
                    str(conversation.group_id) if conversation.group_id is not None else None
                ),
                "customer_contact_id": str(contact.id),
                "source": "whatsapp_external",
            },
        )

        return True

    def _queue_media_processing(
        self,
        *,
        message_id: UUID,
        media: ParsedMetaInboundMedia,
    ) -> None:
        self._repository.add_outbox_event(
            event_type="media.process",
            aggregate_type="message",
            aggregate_id=str(message_id),
            payload_json={
                "message_id": str(message_id),
                "provider_media_id": (media.provider_media_id),
                "original_filename": (media.original_filename),
                "webhook_mime_type": (media.webhook_mime_type),
            },
        )

    async def _resolve_group(
        self,
        whatsapp_number_id: UUID,
    ) -> UUID:
        group_ids = await self._repository.list_active_group_ids_for_number(whatsapp_number_id)

        if not group_ids:
            raise IncomingMessageUnresolvedError("WHATSAPP_NUMBER_HAS_NO_ACTIVE_GROUP")

        if len(group_ids) > 1:
            raise IncomingMessageUnresolvedError("WHATSAPP_NUMBER_GROUP_ROUTE_AMBIGUOUS")

        return group_ids[0]

    async def _reopen_if_required(
        self,
        conversation: Conversation,
    ) -> tuple[Conversation, bool]:
        if conversation.state is not ConversationState.CLOSED:
            return (
                conversation,
                False,
            )

        reopened = await self._repository.reopen_if_closed(conversation.id)

        if reopened is not None:
            return (
                reopened,
                True,
            )

        current = await self._repository.get_conversation_by_id(conversation.id)

        if current is None:
            raise IncomingMessageError("Conversation disappeared during reopen.")

        if current.state is ConversationState.REOPENED:
            return (
                current,
                False,
            )

        raise IncomingMessageError("Conversation changed concurrently during reopen.")

    async def _notify_new_queue(
        self,
        conversation: Conversation,
    ) -> None:
        group_id = conversation.group_id

        if group_id is None:
            raise IncomingMessageUnresolvedError("CONVERSATION_GROUP_MISSING")

        recipient_ids = await self._repository.list_eligible_team_member_ids(group_id)

        self._repository.add_outbox_event(
            event_type="conversation.queued",
            aggregate_type="conversation",
            aggregate_id=str(conversation.id),
            payload_json={
                "conversation_id": str(conversation.id),
                "group_id": str(group_id),
                "recipient_employee_ids": [str(employee_id) for employee_id in recipient_ids],
                "reason": ("new_customer_conversation"),
            },
        )
