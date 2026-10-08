from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from uuid import UUID

from app.authorization.context import (
    AuthorizationContext,
)
from app.authorization.conversation import (
    ConversationAccessResource,
    ConversationActorContext,
    ConversationSendPolicy,
    can_send_message,
)
from app.authorization.errors import (
    AuthorizationDeniedError,
)
from app.authorization.template import (
    TemplateAccessResource,
    TemplateAction,
    TemplateType as AuthorizationTemplateType,
    can_manage_templates,
)
from app.authorization.tenant_isolation import (
    TenantIsolationError,
)
from app.db.models.conversation import (
    Conversation,
    ConversationState,
)
from app.db.models.message import (
    Message,
)
from app.db.models.template import (
    TemplateStatus,
)
from app.repositories.outbound_message import (
    OutboundMessageRepository,
)
from app.repositories.outbox_event import (
    OutboxEventRepository,
)
from app.services.meta_messaging_window import (
    is_free_text_window_open,
)


class OutboundMessageError(RuntimeError):
    pass


class OutboundConversationNotFoundError(OutboundMessageError):
    pass


class OutboundMessageNotAllowedError(OutboundMessageError):
    pass


class MetaMessagingWindowClosedError(OutboundMessageError):
    pass


class InvalidIdempotencyKeyError(OutboundMessageError):
    pass


class IdempotencyKeyConflictError(OutboundMessageError):
    pass


class IdempotencyStateError(OutboundMessageError):
    pass


class OutboundTemplateNotFoundError(OutboundMessageError):
    pass


class OutboundTemplateNotAllowedError(OutboundMessageError):
    pass


class OutboundTemplateNotApprovedError(OutboundMessageError):
    pass


class OutboundTemplateAccountMismatchError(OutboundMessageError):
    pass


class OutboundTemplatePayloadInvalidError(OutboundMessageError):
    pass


class OutboundChannelUnavailableError(OutboundMessageError):
    pass


@dataclass(frozen=True, slots=True)
class OutboundMessageResult:
    message: Message
    idempotent_replay: bool


class OutboundMessageService:
    def __init__(
        self,
        *,
        repository: OutboundMessageRepository,
        outbox_repository: (OutboxEventRepository),
    ) -> None:
        self._repository = repository
        self._outbox_repository = outbox_repository

    async def send_text(
        self,
        *,
        conversation_id: UUID,
        body_text: str,
        context: AuthorizationContext,
        actor: ConversationActorContext,
        idempotency_key: str | None,
    ) -> OutboundMessageResult:
        if not body_text.strip():
            raise (OutboundMessageNotAllowedError("Message body is empty."))

        conversation = await self._load_authorized_conversation(
            conversation_id=(conversation_id),
            context=context,
            actor=actor,
        )

        last_customer_message_at = await self._repository.last_customer_message_at(conversation.id)

        if not is_free_text_window_open(last_customer_message_at=(last_customer_message_at)):
            raise (MetaMessagingWindowClosedError(("Free-text messaging window is closed.")))

        request_hash = self._request_hash(
            conversation_id=(conversation.id),
            body_text=body_text,
        )

        idempotency_row_id = await self._claim_idempotency(
            context=context,
            idempotency_key=(idempotency_key),
            request_hash=request_hash,
        )

        if idempotency_key is not None and idempotency_row_id is None:
            normalized_key = self._validate_idempotency_key(idempotency_key)

            return await self._resolve_idempotent_replay(
                context=context,
                idempotency_key=(normalized_key),
                request_hash=(request_hash),
            )

        message = self._repository.add_pending_text_message(
            conversation_id=(conversation.id),
            body_text=body_text,
            actual_actor_id=(actor.employee_id),
        )

        await self._finish_pending_message(
            message=message,
            idempotency_row_id=(idempotency_row_id),
        )

        return OutboundMessageResult(
            message=message,
            idempotent_replay=False,
        )

    async def send_template(
        self,
        *,
        conversation_id: UUID,
        template_id: UUID,
        components: list[dict[str, object]],
        context: AuthorizationContext,
        actor: ConversationActorContext,
        idempotency_key: str | None,
    ) -> OutboundMessageResult:
        self._validate_template_components(components)

        conversation = await self._load_authorized_conversation(
            conversation_id=(conversation_id),
            context=context,
            actor=actor,
        )

        template = await self._repository.get_meta_template(template_id)

        if template is None:
            raise (OutboundTemplateNotFoundError)

        self._authorize_template_send(
            context=context,
            tenant_id=template.tenant_id,
        )

        if template.status is not TemplateStatus.APPROVED:
            raise (OutboundTemplateNotApprovedError)

        whatsapp_number = await self._repository.get_active_whatsapp_number(
            conversation.whatsapp_number_id
        )

        if whatsapp_number is None:
            raise (OutboundChannelUnavailableError)

        if template.meta_account_id != whatsapp_number.integration_id:
            raise (OutboundTemplateAccountMismatchError)

        request_hash = self._template_request_hash(
            conversation_id=(conversation.id),
            template_id=template.id,
            components=components,
        )

        idempotency_row_id = await self._claim_idempotency(
            context=context,
            idempotency_key=(idempotency_key),
            request_hash=request_hash,
        )

        if idempotency_key is not None and idempotency_row_id is None:
            normalized_key = self._validate_idempotency_key(idempotency_key)

            return await self._resolve_idempotent_replay(
                context=context,
                idempotency_key=(normalized_key),
                request_hash=(request_hash),
            )

        message = self._repository.add_pending_template_message(
            conversation_id=(conversation.id),
            template_id=template.id,
            components=components,
            actual_actor_id=(actor.employee_id),
        )

        await self._finish_pending_message(
            message=message,
            idempotency_row_id=(idempotency_row_id),
        )

        return OutboundMessageResult(
            message=message,
            idempotent_replay=False,
        )

    async def _load_authorized_conversation(
        self,
        *,
        conversation_id: UUID,
        context: AuthorizationContext,
        actor: ConversationActorContext,
    ) -> Conversation:
        conversation = await self._repository.get_conversation(conversation_id)

        if conversation is None:
            raise (OutboundConversationNotFoundError)

        if conversation.group_id is None:
            raise (OutboundMessageNotAllowedError("Conversation has no group."))

        if conversation.state is ConversationState.CLOSED:
            raise (OutboundMessageNotAllowedError(("Cannot send to a closed conversation.")))

        group = await self._repository.get_active_group(conversation.group_id)

        if group is None:
            raise (OutboundMessageNotAllowedError(("Conversation group is inactive.")))

        resource = ConversationAccessResource(
            tenant_id=(conversation.tenant_id),
            group_id=(conversation.group_id),
            responsible_employee_id=(conversation.responsible_employee_id),
            is_queued=(conversation.state is ConversationState.QUEUED),
        )

        policy = ConversationSendPolicy(
            allow_non_owner_employee_send=(group.allow_non_owner_employee_send),
        )

        if not self._can_send_for_any_role(
            context=context,
            actor=actor,
            resource=resource,
            policy=policy,
        ):
            raise (OutboundMessageNotAllowedError(("Actor cannot send in conversation.")))

        return conversation

    async def _claim_idempotency(
        self,
        *,
        context: AuthorizationContext,
        idempotency_key: str | None,
        request_hash: str,
    ) -> UUID | None:
        if idempotency_key is None:
            return None

        normalized_key = self._validate_idempotency_key(idempotency_key)

        return await self._repository.try_claim_idempotency_key(
            actor_id=context.actor_id,
            idempotency_key=(normalized_key),
            request_hash=request_hash,
        )

    async def _finish_pending_message(
        self,
        *,
        message: Message,
        idempotency_row_id: UUID | None,
    ) -> None:
        if idempotency_row_id is not None:
            await self._repository.bind_idempotency_message(
                idempotency_row_id=(idempotency_row_id),
                message_id=message.id,
            )

        self._outbox_repository.add_event(
            event_type="meta.outbound.send",
            aggregate_type="message",
            aggregate_id=str(message.id),
            payload_json={
                "message_id": str(message.id),
            },
        )

    async def _resolve_idempotent_replay(
        self,
        *,
        context: AuthorizationContext,
        idempotency_key: str,
        request_hash: str,
    ) -> OutboundMessageResult:
        existing = await self._repository.get_idempotency_key(
            actor_id=context.actor_id,
            idempotency_key=(idempotency_key),
        )

        if existing is None:
            raise IdempotencyStateError(("Idempotency row disappeared after conflict."))

        if existing.request_hash != request_hash:
            raise (
                IdempotencyKeyConflictError(
                    ("Idempotency-Key was already used for another request.")
                )
            )

        if existing.message_id is None:
            raise IdempotencyStateError(("Idempotency row has no associated message."))

        message = await self._repository.get_message(existing.message_id)

        if message is None:
            raise IdempotencyStateError(("Idempotent message could not be loaded."))

        return OutboundMessageResult(
            message=message,
            idempotent_replay=True,
        )

    def _authorize_template_send(
        self,
        *,
        context: AuthorizationContext,
        tenant_id: UUID,
    ) -> None:
        resource = TemplateAccessResource(
            tenant_id=tenant_id,
            template_type=(AuthorizationTemplateType.META),
        )

        try:
            allowed = can_manage_templates(
                context,
                resource,
                TemplateAction.SEND,
            )
        except (
            AuthorizationDeniedError,
            TenantIsolationError,
        ) as exc:
            raise (OutboundTemplateNotAllowedError) from exc

        if not allowed:
            raise (OutboundTemplateNotAllowedError)

    @staticmethod
    def _validate_template_components(
        components: list[dict[str, object]],
    ) -> None:
        for component in components:
            raw_type = component.get("type")

            if (
                not isinstance(
                    raw_type,
                    str,
                )
                or not raw_type.strip()
            ):
                raise (
                    OutboundTemplatePayloadInvalidError(
                        ("Each template component requires a non-empty type.")
                    )
                )

    @staticmethod
    def _validate_idempotency_key(
        value: str,
    ) -> str:
        normalized = value.strip()

        if not normalized:
            raise (InvalidIdempotencyKeyError("Idempotency-Key is empty."))

        if len(normalized) > 255:
            raise (InvalidIdempotencyKeyError(("Idempotency-Key exceeds 255 characters.")))

        return normalized

    @staticmethod
    def _request_hash(
        *,
        conversation_id: UUID,
        body_text: str,
    ) -> str:
        canonical = json.dumps(
            {
                "conversation_id": str(conversation_id),
                "message_type": "text",
                "body_text": body_text,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")

        return hashlib.sha256(canonical).hexdigest()

    @staticmethod
    def _template_request_hash(
        *,
        conversation_id: UUID,
        template_id: UUID,
        components: list[dict[str, object]],
    ) -> str:
        canonical = json.dumps(
            {
                "conversation_id": str(conversation_id),
                "message_type": "template",
                "template_id": str(template_id),
                "components": components,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")

        return hashlib.sha256(canonical).hexdigest()

    @staticmethod
    def _can_send_for_any_role(
        *,
        context: AuthorizationContext,
        actor: ConversationActorContext,
        resource: ConversationAccessResource,
        policy: ConversationSendPolicy,
    ) -> bool:
        for role in context.roles:
            single_role_context = AuthorizationContext(
                actor_id=(context.actor_id),
                role=role,
                tenant_id=(context.tenant_id),
            )

            try:
                allowed = can_send_message(
                    single_role_context,
                    actor,
                    resource,
                    policy,
                )
            except AuthorizationDeniedError:
                continue
            except TenantIsolationError:
                raise

            if allowed:
                return True

        return False
