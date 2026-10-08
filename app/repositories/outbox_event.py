from __future__ import annotations

from app.db.models.outbox_event import OutboxEvent
from app.repositories.base import TenantScopedRepository


class OutboxEventRepository(TenantScopedRepository):
    def add_event(
        self,
        *,
        event_type: str,
        aggregate_type: str,
        aggregate_id: str,
        payload_json: dict[str, object],
    ) -> OutboxEvent:
        event = OutboxEvent(
            tenant_id=self.tenant_id,
            event_type=event_type,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            payload_json=payload_json,
        )

        self._session.add(event)

        return event
