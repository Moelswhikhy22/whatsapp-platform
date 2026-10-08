from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

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
    OutgoingWebhookDelivery,
    OutgoingWebhookDeliveryAttempt,
    OutgoingWebhookDeliveryStatus,
)
from app.repositories.outbox_event import (
    OutboxEventRepository,
)
from app.repositories.outgoing_webhook import (
    OutgoingWebhookRepository,
)


OUTGOING_WEBHOOK_RETRY_REQUESTED_EVENT = "outgoing_webhook.retry_requested"


class OutgoingWebhookManagementError(RuntimeError):
    pass


class OutgoingWebhookDeliveryNotFoundError(OutgoingWebhookManagementError):
    pass


class OutgoingWebhookDeliveryRetryConflictError(OutgoingWebhookManagementError):
    pass


class OutgoingWebhookManagementService:
    def __init__(
        self,
        *,
        repository: (OutgoingWebhookRepository),
        outbox_repository: (OutboxEventRepository),
    ) -> None:
        self._repository = repository
        self._outbox_repository = outbox_repository

    def _authorize(
        self,
        context: AuthorizationContext,
    ) -> None:
        ensure_same_tenant(
            context.tenant_id,
            self._repository.tenant_id,
        )

        ensure_same_tenant(
            self._repository.tenant_id,
            self._outbox_repository.tenant_id,
        )

        require_permission(
            context,
            Permission.WEBHOOK_MANAGE,
        )

    async def list_deliveries(
        self,
        *,
        context: AuthorizationContext,
        subscription_id: UUID | None,
        status: (OutgoingWebhookDeliveryStatus | None),
        limit: int,
        offset: int,
    ) -> list[OutgoingWebhookDelivery]:
        self._authorize(context)

        return await self._repository.list_deliveries(
            subscription_id=(subscription_id),
            status=status,
            limit=limit,
            offset=offset,
        )

    async def list_attempts(
        self,
        *,
        context: AuthorizationContext,
        delivery_id: UUID,
    ) -> list[OutgoingWebhookDeliveryAttempt]:
        self._authorize(context)

        delivery = await self._repository.get_delivery(delivery_id=delivery_id)

        if delivery is None:
            raise (
                OutgoingWebhookDeliveryNotFoundError(("Outgoing webhook delivery was not found."))
            )

        return await self._repository.list_delivery_attempts(delivery_id=delivery_id)

    async def retry_failed_delivery(
        self,
        *,
        context: AuthorizationContext,
        delivery_id: UUID,
    ) -> OutgoingWebhookDelivery:
        self._authorize(context)

        delivery = await self._repository.lock_delivery(delivery_id=delivery_id)

        if delivery is None:
            raise (
                OutgoingWebhookDeliveryNotFoundError(("Outgoing webhook delivery was not found."))
            )

        if delivery.status is not (OutgoingWebhookDeliveryStatus.FAILED):
            raise (
                OutgoingWebhookDeliveryRetryConflictError(
                    ("Only failed webhook deliveries can be manually retried.")
                )
            )

        delivery.status = OutgoingWebhookDeliveryStatus.PENDING

        delivery.next_attempt_at = datetime.now(UTC)

        delivery.delivered_at = None

        self._outbox_repository.add_event(
            event_type=(OUTGOING_WEBHOOK_RETRY_REQUESTED_EVENT),
            aggregate_type=("outgoing_webhook_delivery"),
            aggregate_id=str(delivery.id),
            payload_json={
                "delivery_id": str(delivery.id),
                "original_event_id": str(delivery.event_id),
            },
        )

        await self._repository.flush()

        return delivery
