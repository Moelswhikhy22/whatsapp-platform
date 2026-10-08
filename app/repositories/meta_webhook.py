from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import (
    insert as pg_insert,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.integration import (
    Integration,
    IntegrationProvider,
)
from app.db.models.outbox_event import OutboxEvent
from app.db.models.raw_webhook_event import (
    RawWebhookEvent,
    RawWebhookProcessingStatus,
    RawWebhookProvider,
)
from app.db.models.whatsapp_number import (
    WhatsAppNumber,
)


class MetaWebhookRepository:
    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self._session = session

    async def get_active_meta_integration(
        self,
        integration_id: UUID,
    ) -> Integration | None:
        statement = select(Integration).where(
            Integration.id == integration_id,
            Integration.provider == IntegrationProvider.META,
            Integration.active.is_(True),
        )

        result = await self._session.scalars(statement)

        return result.first()

    async def get_active_whatsapp_numbers(
        self,
        meta_phone_number_ids: set[str],
    ) -> list[WhatsAppNumber]:
        if not meta_phone_number_ids:
            return []

        statement = select(WhatsAppNumber).where(
            WhatsAppNumber.meta_phone_number_id.in_(meta_phone_number_ids),
            WhatsAppNumber.active.is_(True),
        )

        result = await self._session.scalars(statement)

        return list(result.all())

    async def insert_raw_event_if_new(
        self,
        *,
        tenant_id: UUID | None,
        provider_event_key: str,
        event_type: str | None,
        payload_json: dict[str, object],
        processing_status: (RawWebhookProcessingStatus),
        last_error: str | None,
    ) -> UUID | None:
        raw_event_id = uuid4()

        statement = (
            pg_insert(RawWebhookEvent)
            .values(
                id=raw_event_id,
                tenant_id=tenant_id,
                provider=RawWebhookProvider.META,
                provider_event_key=(provider_event_key),
                event_type=event_type,
                payload_json=payload_json,
                processing_status=(processing_status),
                attempts=0,
                last_error=last_error,
            )
            .on_conflict_do_nothing(
                constraint=("uq_raw_webhook_events_provider_event_key"),
            )
            .returning(RawWebhookEvent.id)
        )

        result = await self._session.execute(statement)

        return result.scalar_one_or_none()

    def add_inbound_outbox_event(
        self,
        *,
        tenant_id: UUID,
        raw_event_id: UUID,
    ) -> OutboxEvent:
        event = OutboxEvent(
            tenant_id=tenant_id,
            event_type=("meta.inbound.raw_event"),
            aggregate_type=("raw_webhook_event"),
            aggregate_id=str(raw_event_id),
            payload_json={
                "raw_event_id": str(raw_event_id),
            },
        )

        self._session.add(event)

        return event
