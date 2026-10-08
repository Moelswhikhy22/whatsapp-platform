from __future__ import annotations

from uuid import UUID, uuid4

from app.authorization.context import (
    AuthorizationContext,
)
from app.authorization.permissions import (
    Permission,
)
from app.authorization.policy import (
    require_permission,
)
from app.authorization.tenant_isolation import (
    ensure_same_tenant,
)
from app.db.models.outgoing_webhook import (
    OutgoingWebhookSubscription,
)
from app.integrations.vault.client import (
    VaultClient,
)
from app.integrations.vault.paths import (
    VaultPathBuilder,
)
from app.integrations.webhooks.ssrf import (
    WebhookEndpointValidator,
)
from app.repositories.outgoing_webhook import (
    OutgoingWebhookRepository,
)
from uuid import UUID, uuid4
from app.repositories.business_audit_log import (
    BusinessAuditLogRepository,
)

SUPPORTED_OUTGOING_WEBHOOK_EVENTS = frozenset(
    {
        "message.received",
        "message.sent",
        "message.delivered",
        "message.read",
        "message.failed",
        "conversation.queued",
        "conversation.claimed",
        "conversation.reassigned",
        "conversation.transferred",
        "conversation.closed",
        "conversation.reopened",
    }
)


class OutgoingWebhookSubscriptionError(RuntimeError):
    pass


class OutgoingWebhookSubscriptionInvalidError(OutgoingWebhookSubscriptionError):
    pass


class OutgoingWebhookSecretStorageError(OutgoingWebhookSubscriptionError):
    pass


class OutgoingWebhookPersistenceError(OutgoingWebhookSubscriptionError):
    pass


class OutgoingWebhookSubscriptionService:
    def __init__(
        self,
        *,
        repository: OutgoingWebhookRepository,
        audit_repository: BusinessAuditLogRepository,
        vault_client: VaultClient,
        path_builder: VaultPathBuilder,
        endpoint_validator: WebhookEndpointValidator,
    ) -> None:
        self._repository = repository
        self._audit_repository = audit_repository
        self._vault_client = vault_client
        self._path_builder = path_builder
        self._endpoint_validator = endpoint_validator

    async def create(
        self,
        *,
        context: AuthorizationContext,
        name: str,
        endpoint_url: str,
        event_types: list[str],
        signing_secret: str,
    ) -> OutgoingWebhookSubscription:
        ensure_same_tenant(
            context.tenant_id,
            self._repository.tenant_id,
        )

        require_permission(
            context,
            Permission.WEBHOOK_MANAGE,
        )

        normalized_name = name.strip()

        if not normalized_name:
            raise (OutgoingWebhookSubscriptionInvalidError("Webhook name must not be blank."))

        normalized_events = self._normalize_events(event_types)

        if len(signing_secret) < 32:
            raise (
                OutgoingWebhookSubscriptionInvalidError(
                    ("Webhook signing secret must contain at least 32 characters.")
                )
            )

        normalized_url = await self._endpoint_validator.validate(endpoint_url)

        subscription_id = uuid4()
        secret_version_id = uuid4()

        secret_reference = self._path_builder.outgoing_webhook_signing_secret(
            tenant_id=(self._repository.tenant_id),
            subscription_id=(subscription_id),
            secret_version_id=(secret_version_id),
        )

        try:
            await self._vault_client.write_secret(
                path=secret_reference,
                secret={"signing_secret": (signing_secret)},
            )

        except Exception as exc:
            raise (
                OutgoingWebhookSecretStorageError(("Webhook signing secret could not be stored."))
            ) from exc

        subscription = self._repository.add_subscription(
            subscription_id=(subscription_id),
            name=normalized_name,
            endpoint_url=normalized_url,
            event_types=list(normalized_events),
            vault_secret_reference=(secret_reference),
        )
        self._audit_repository.add_outgoing_webhook_created(
            subscription_id=subscription_id,
            actor_id=context.actor_id,
            trace_id=uuid4().hex,
            name=normalized_name,
            event_types=list(normalized_events),
        )

        try:
            await self._repository.flush()

        except Exception as exc:
            try:
                await self._vault_client.delete_latest_secret_version(path=secret_reference)
            except Exception:
                pass

            raise (
                OutgoingWebhookPersistenceError(("Webhook subscription could not be persisted."))
            ) from exc

        return subscription

    async def list(
        self,
        *,
        context: AuthorizationContext,
    ) -> list[OutgoingWebhookSubscription]:
        ensure_same_tenant(
            context.tenant_id,
            self._repository.tenant_id,
        )

        require_permission(
            context,
            Permission.WEBHOOK_MANAGE,
        )

        return await self._repository.list_subscriptions()

    @staticmethod
    def _normalize_events(
        event_types: list[str],
    ) -> tuple[str, ...]:
        normalized = tuple(
            dict.fromkeys(event.strip().lower() for event in event_types if event.strip())
        )

        if not normalized:
            raise (
                OutgoingWebhookSubscriptionInvalidError(
                    ("At least one webhook event type is required.")
                )
            )

        unsupported = set(normalized) - SUPPORTED_OUTGOING_WEBHOOK_EVENTS

        if unsupported:
            raise (OutgoingWebhookSubscriptionInvalidError(("Unsupported webhook event type.")))

        return normalized
