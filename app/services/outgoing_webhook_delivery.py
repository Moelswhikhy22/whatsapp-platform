from __future__ import annotations

from dataclasses import dataclass
from datetime import (
    UTC,
    datetime,
    timedelta,
)
from uuid import UUID

from app.db.models.outgoing_webhook import (
    OutgoingWebhookAttemptOutcome,
    OutgoingWebhookDelivery,
    OutgoingWebhookDeliveryStatus,
    OutgoingWebhookSubscription,
)
from app.integrations.webhooks.delivery import (
    WebhookDeliveryOutcome,
    WebhookDeliveryResult,
    WebhookHttpDeliveryClient,
)
from app.integrations.webhooks.signing_secret import (
    VaultWebhookSigningSecretProvider,
    WebhookSigningSecretInvalidError,
    WebhookSigningSecretUnavailableError,
)
from app.repositories.outgoing_webhook import (
    OutgoingWebhookDeliveryRepository,
)
from app.services.outgoing_webhook_subscription import (
    SUPPORTED_OUTGOING_WEBHOOK_EVENTS,
)


RETRY_DELAY_SECONDS = 5


class OutgoingWebhookDeliveryError(RuntimeError):
    pass


class OutgoingWebhookRetryDeliveryNotFoundError(OutgoingWebhookDeliveryError):
    pass


@dataclass(
    frozen=True,
    slots=True,
)
class OutgoingWebhookEvent:
    event_id: UUID
    tenant_id: UUID
    event_type: str
    aggregate_type: str
    aggregate_id: str
    occurred_at: str
    payload: dict[str, object]

    def delivery_payload(
        self,
    ) -> dict[str, object]:
        return {
            "id": str(self.event_id),
            "type": self.event_type,
            "occurred_at": (self.occurred_at),
            "resource": {
                "type": (self.aggregate_type),
                "id": (self.aggregate_id),
            },
            "data": self.payload,
        }


@dataclass(
    frozen=True,
    slots=True,
)
class OutgoingWebhookRetryRequest:
    tenant_id: UUID
    delivery_id: UUID


@dataclass(
    frozen=True,
    slots=True,
)
class OutgoingWebhookProcessResult:
    matched_subscriptions: int
    attempted_deliveries: int
    delivered: int
    failed: int
    retry_required: bool


class OutgoingWebhookDeliveryService:
    def __init__(
        self,
        *,
        repository: (OutgoingWebhookDeliveryRepository),
        signing_secret_provider: (VaultWebhookSigningSecretProvider),
        delivery_client: (WebhookHttpDeliveryClient),
    ) -> None:
        self._repository = repository
        self._signing_secret_provider = signing_secret_provider
        self._delivery_client = delivery_client

    async def process_event(
        self,
        *,
        event: OutgoingWebhookEvent,
        final_attempt: bool = False,
    ) -> OutgoingWebhookProcessResult:
        if event.tenant_id != self._repository.tenant_id:
            raise ValueError(("Outgoing webhook event tenant does not match repository tenant."))

        if event.event_type not in (SUPPORTED_OUTGOING_WEBHOOK_EVENTS):
            return self._empty_result()

        subscriptions = await self._repository.list_active_subscriptions_for_event(
            event_type=(event.event_type)
        )

        delivery_payload = event.delivery_payload()

        attempted = 0
        delivered_count = 0
        failed_count = 0
        retry_required = False

        for subscription in subscriptions:
            delivery = await self._repository.get_or_create_delivery(
                subscription_id=(subscription.id),
                event_id=event.event_id,
                event_type=(event.event_type),
                payload_json=(delivery_payload),
            )

            locked_delivery = await self._repository.lock_delivery(delivery_id=delivery.id)

            if locked_delivery is None:
                raise RuntimeError(("Outgoing webhook delivery disappeared while processing."))

            if locked_delivery.status is not (OutgoingWebhookDeliveryStatus.PENDING):
                continue

            attempted += 1

            result = await self._attempt_delivery(
                subscription=subscription,
                tenant_id=(event.tenant_id),
                event_id=(event.event_id),
                event_type=(event.event_type),
                payload=(delivery_payload),
            )

            (
                was_delivered,
                was_failed,
                needs_retry,
            ) = self._apply_attempt_result(
                delivery=(locked_delivery),
                result=result,
                final_attempt=(final_attempt),
            )

            delivered_count += int(was_delivered)

            failed_count += int(was_failed)

            retry_required = retry_required or needs_retry

        await self._repository.flush()

        return OutgoingWebhookProcessResult(
            matched_subscriptions=(len(subscriptions)),
            attempted_deliveries=(attempted),
            delivered=(delivered_count),
            failed=failed_count,
            retry_required=(retry_required),
        )

    async def process_retry_request(
        self,
        *,
        request: (OutgoingWebhookRetryRequest),
        final_attempt: bool = False,
    ) -> OutgoingWebhookProcessResult:
        if request.tenant_id != self._repository.tenant_id:
            raise ValueError(("Outgoing webhook retry tenant does not match repository tenant."))

        delivery = await self._repository.lock_delivery(delivery_id=(request.delivery_id))

        if delivery is None:
            raise (
                OutgoingWebhookRetryDeliveryNotFoundError(
                    ("Outgoing webhook retry delivery was not found.")
                )
            )

        # Duplicate control messages are safe.
        #
        # A manual retry changes FAILED -> PENDING
        # before creating the outbox command.
        #
        # If the same command is delivered again
        # after the delivery was already completed,
        # no second HTTP call is made.
        if delivery.status is not (OutgoingWebhookDeliveryStatus.PENDING):
            return self._empty_result()

        subscription = await self._repository.get_subscription(
            subscription_id=(delivery.subscription_id)
        )

        if subscription is None:
            result = WebhookDeliveryResult(
                outcome=(WebhookDeliveryOutcome.PERMANENT_FAILURE),
                http_status_code=None,
                error_code=("WEBHOOK_SUBSCRIPTION_NOT_FOUND"),
            )

        elif not subscription.active:
            result = WebhookDeliveryResult(
                outcome=(WebhookDeliveryOutcome.PERMANENT_FAILURE),
                http_status_code=None,
                error_code=("WEBHOOK_SUBSCRIPTION_INACTIVE"),
            )

        else:
            result = await self._attempt_delivery(
                subscription=(subscription),
                tenant_id=(request.tenant_id),
                event_id=(delivery.event_id),
                event_type=(delivery.event_type),
                payload=(delivery.payload_json),
            )

        (
            was_delivered,
            was_failed,
            needs_retry,
        ) = self._apply_attempt_result(
            delivery=delivery,
            result=result,
            final_attempt=(final_attempt),
        )

        await self._repository.flush()

        return OutgoingWebhookProcessResult(
            matched_subscriptions=1,
            attempted_deliveries=1,
            delivered=int(was_delivered),
            failed=int(was_failed),
            retry_required=(needs_retry),
        )

    async def _attempt_delivery(
        self,
        *,
        subscription: (OutgoingWebhookSubscription),
        tenant_id: UUID,
        event_id: UUID,
        event_type: str,
        payload: dict[str, object],
    ) -> WebhookDeliveryResult:
        try:
            signing_secret = await self._signing_secret_provider.get_secret(
                tenant_id=tenant_id,
                subscription=(subscription),
            )

        except WebhookSigningSecretInvalidError:
            return WebhookDeliveryResult(
                outcome=(WebhookDeliveryOutcome.PERMANENT_FAILURE),
                http_status_code=None,
                error_code=("WEBHOOK_SIGNING_SECRET_INVALID"),
            )

        except WebhookSigningSecretUnavailableError:
            return WebhookDeliveryResult(
                outcome=(WebhookDeliveryOutcome.RETRYABLE_FAILURE),
                http_status_code=None,
                error_code=("WEBHOOK_SIGNING_SECRET_UNAVAILABLE"),
            )

        return await self._delivery_client.deliver(
            endpoint_url=(subscription.endpoint_url),
            event_id=event_id,
            event_type=event_type,
            payload=payload,
            signing_secret=(signing_secret.value),
        )

    def _apply_attempt_result(
        self,
        *,
        delivery: (OutgoingWebhookDelivery),
        result: WebhookDeliveryResult,
        final_attempt: bool,
    ) -> tuple[
        bool,
        bool,
        bool,
    ]:
        attempt_number = delivery.attempt_count + 1

        now = datetime.now(UTC)

        delivery.attempt_count = attempt_number

        delivery.last_attempt_at = now

        delivery.last_http_status_code = result.http_status_code

        delivery.last_error = result.error_code

        was_delivered = False
        was_failed = False
        retry_required = False

        if result.outcome is WebhookDeliveryOutcome.DELIVERED:
            delivery.status = OutgoingWebhookDeliveryStatus.DELIVERED

            delivery.delivered_at = now

            delivery.next_attempt_at = now

            attempt_outcome = OutgoingWebhookAttemptOutcome.SUCCEEDED

            was_delivered = True

        elif result.outcome is WebhookDeliveryOutcome.RETRYABLE_FAILURE:
            delivery.delivered_at = None

            attempt_outcome = OutgoingWebhookAttemptOutcome.FAILED

            retry_required = True

            if final_attempt:
                delivery.status = OutgoingWebhookDeliveryStatus.FAILED

                delivery.next_attempt_at = now

                was_failed = True

            else:
                delivery.status = OutgoingWebhookDeliveryStatus.PENDING

                delivery.next_attempt_at = now + timedelta(seconds=(RETRY_DELAY_SECONDS))

        else:
            delivery.status = OutgoingWebhookDeliveryStatus.FAILED

            delivery.delivered_at = None

            delivery.next_attempt_at = now

            attempt_outcome = OutgoingWebhookAttemptOutcome.FAILED

            was_failed = True

        self._repository.add_attempt(
            delivery_id=(delivery.id),
            attempt_number=(attempt_number),
            outcome=attempt_outcome,
            http_status_code=(result.http_status_code),
            error_message=(result.error_code),
        )

        return (
            was_delivered,
            was_failed,
            retry_required,
        )

    @staticmethod
    def _empty_result() -> OutgoingWebhookProcessResult:
        return OutgoingWebhookProcessResult(
            matched_subscriptions=0,
            attempted_deliveries=0,
            delivered=0,
            failed=0,
            retry_required=False,
        )
