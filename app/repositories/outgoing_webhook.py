from __future__ import annotations

from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.outgoing_webhook import (
    OutgoingWebhookAttemptOutcome,
    OutgoingWebhookDelivery,
    OutgoingWebhookDeliveryAttempt,
    OutgoingWebhookDeliveryStatus,
    OutgoingWebhookSubscription,
)
from app.repositories.base import (
    TenantScopedRepository,
)


class OutgoingWebhookRepository(TenantScopedRepository):
    async def list_subscriptions(
        self,
    ) -> list[OutgoingWebhookSubscription]:
        statement: Select[OutgoingWebhookSubscription] = self._scope(
            select(OutgoingWebhookSubscription),
            (OutgoingWebhookSubscription.tenant_id),
        ).order_by((OutgoingWebhookSubscription.created_at.desc()))

        result = await self._session.scalars(statement)

        return list(result.all())

    async def get_subscription(
        self,
        subscription_id: UUID,
    ) -> OutgoingWebhookSubscription | None:
        statement: Select[OutgoingWebhookSubscription] = self._scope(
            select(OutgoingWebhookSubscription),
            (OutgoingWebhookSubscription.tenant_id),
        ).where((OutgoingWebhookSubscription.id == subscription_id))

        result = await self._session.scalars(statement)

        return result.first()

    def add_subscription(
        self,
        *,
        subscription_id: UUID,
        name: str,
        endpoint_url: str,
        event_types: list[str],
        vault_secret_reference: str,
    ) -> OutgoingWebhookSubscription:
        subscription = OutgoingWebhookSubscription(
            id=subscription_id,
            tenant_id=self.tenant_id,
            name=name,
            endpoint_url=endpoint_url,
            event_types_json=(event_types),
            vault_secret_reference=(vault_secret_reference),
            active=True,
        )

        self._session.add(subscription)

        return subscription

    async def list_deliveries(
        self,
        *,
        subscription_id: UUID | None,
        status: (OutgoingWebhookDeliveryStatus | None),
        limit: int,
        offset: int,
    ) -> list[OutgoingWebhookDelivery]:
        statement = self._scope(
            select(OutgoingWebhookDelivery),
            (OutgoingWebhookDelivery.tenant_id),
        )

        if subscription_id is not None:
            statement = statement.where(
                (OutgoingWebhookDelivery.subscription_id == subscription_id)
            )

        if status is not None:
            statement = statement.where((OutgoingWebhookDelivery.status == status))

        statement = (
            statement.order_by((OutgoingWebhookDelivery.created_at.desc()))
            .limit(limit)
            .offset(offset)
        )

        result = await self._session.scalars(statement)

        return list(result.all())

    async def get_delivery(
        self,
        *,
        delivery_id: UUID,
    ) -> OutgoingWebhookDelivery | None:
        statement = self._scope(
            select(OutgoingWebhookDelivery),
            (OutgoingWebhookDelivery.tenant_id),
        ).where((OutgoingWebhookDelivery.id == delivery_id))

        result = await self._session.scalars(statement)

        return result.first()

    async def lock_delivery(
        self,
        *,
        delivery_id: UUID,
    ) -> OutgoingWebhookDelivery | None:
        statement = (
            self._scope(
                select(OutgoingWebhookDelivery),
                (OutgoingWebhookDelivery.tenant_id),
            )
            .where((OutgoingWebhookDelivery.id == delivery_id))
            .with_for_update()
        )

        result = await self._session.scalars(statement)

        return result.first()

    async def list_delivery_attempts(
        self,
        *,
        delivery_id: UUID,
    ) -> list[OutgoingWebhookDeliveryAttempt]:
        statement = (
            self._scope(
                select(OutgoingWebhookDeliveryAttempt),
                (OutgoingWebhookDeliveryAttempt.tenant_id),
            )
            .where((OutgoingWebhookDeliveryAttempt.delivery_id == delivery_id))
            .order_by((OutgoingWebhookDeliveryAttempt.attempt_number.asc()))
        )

        result = await self._session.scalars(statement)

        return list(result.all())

    async def flush(self) -> None:
        await self._session.flush()


class OutgoingWebhookDeliveryRepository:
    """
    Worker-side tenant-scoped repository.

    The tenant ID comes from the trusted transactional
    outbox/RabbitMQ envelope, never from an HTTP request.
    Every query still explicitly includes tenant_id.
    """

    def __init__(
        self,
        *,
        session: AsyncSession,
        tenant_id: UUID,
    ) -> None:
        self._session = session
        self._tenant_id = tenant_id

    @property
    def tenant_id(self) -> UUID:
        return self._tenant_id

    async def list_active_subscriptions_for_event(
        self,
        *,
        event_type: str,
    ) -> list[OutgoingWebhookSubscription]:
        statement = (
            select(OutgoingWebhookSubscription)
            .where(
                (OutgoingWebhookSubscription.tenant_id == self._tenant_id),
                (OutgoingWebhookSubscription.active.is_(True)),
                (OutgoingWebhookSubscription.event_types_json.contains([event_type])),
            )
            .order_by((OutgoingWebhookSubscription.created_at.asc()))
        )

        result = await self._session.scalars(statement)

        return list(result.all())

    async def get_subscription(
        self,
        *,
        subscription_id: UUID,
    ) -> OutgoingWebhookSubscription | None:
        statement = select(OutgoingWebhookSubscription).where(
            (OutgoingWebhookSubscription.tenant_id == self._tenant_id),
            (OutgoingWebhookSubscription.id == subscription_id),
        )

        result = await self._session.scalars(statement)

        return result.first()

    async def get_or_create_delivery(
        self,
        *,
        subscription_id: UUID,
        event_id: UUID,
        event_type: str,
        payload_json: dict[str, object],
    ) -> OutgoingWebhookDelivery:
        statement = (
            insert(OutgoingWebhookDelivery)
            .values(
                tenant_id=self._tenant_id,
                subscription_id=(subscription_id),
                event_id=event_id,
                event_type=event_type,
                payload_json=(payload_json),
            )
            .on_conflict_do_nothing(
                index_elements=[
                    (OutgoingWebhookDelivery.tenant_id),
                    (OutgoingWebhookDelivery.subscription_id),
                    (OutgoingWebhookDelivery.event_id),
                ]
            )
            .returning(OutgoingWebhookDelivery.id)
        )

        result = await self._session.execute(statement)

        created_id = result.scalar_one_or_none()

        if created_id is not None:
            delivery = await self.get_delivery(delivery_id=created_id)

            if delivery is None:
                raise RuntimeError(("Created outgoing webhook delivery could not be reloaded."))

            return delivery

        existing = await self.get_delivery_by_event(
            subscription_id=(subscription_id),
            event_id=event_id,
        )

        if existing is None:
            raise RuntimeError(
                (
                    "Outgoing webhook delivery "
                    "conflict occurred but the "
                    "existing delivery could "
                    "not be loaded."
                )
            )

        return existing

    async def get_delivery(
        self,
        *,
        delivery_id: UUID,
    ) -> OutgoingWebhookDelivery | None:
        statement = select(OutgoingWebhookDelivery).where(
            (OutgoingWebhookDelivery.tenant_id == self._tenant_id),
            (OutgoingWebhookDelivery.id == delivery_id),
        )

        result = await self._session.scalars(statement)

        return result.first()

    async def get_delivery_by_event(
        self,
        *,
        subscription_id: UUID,
        event_id: UUID,
    ) -> OutgoingWebhookDelivery | None:
        statement = select(OutgoingWebhookDelivery).where(
            (OutgoingWebhookDelivery.tenant_id == self._tenant_id),
            (OutgoingWebhookDelivery.subscription_id == subscription_id),
            (OutgoingWebhookDelivery.event_id == event_id),
        )

        result = await self._session.scalars(statement)

        return result.first()

    async def lock_delivery(
        self,
        *,
        delivery_id: UUID,
    ) -> OutgoingWebhookDelivery | None:
        statement = (
            select(OutgoingWebhookDelivery)
            .where(
                (OutgoingWebhookDelivery.tenant_id == self._tenant_id),
                (OutgoingWebhookDelivery.id == delivery_id),
            )
            .with_for_update()
        )

        result = await self._session.scalars(statement)

        return result.first()

    def add_attempt(
        self,
        *,
        delivery_id: UUID,
        attempt_number: int,
        outcome: (OutgoingWebhookAttemptOutcome),
        http_status_code: int | None,
        error_message: str | None,
    ) -> OutgoingWebhookDeliveryAttempt:
        attempt = OutgoingWebhookDeliveryAttempt(
            tenant_id=self._tenant_id,
            delivery_id=delivery_id,
            attempt_number=(attempt_number),
            outcome=outcome,
            http_status_code=(http_status_code),
            error_message=(error_message),
        )

        self._session.add(attempt)

        return attempt

    async def flush(self) -> None:
        await self._session.flush()
