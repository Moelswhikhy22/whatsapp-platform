from __future__ import annotations

from uuid import UUID

from app.audit_payload import (
    sanitize_audit_payload,
)
from app.db.models.business_audit_log import (
    BusinessAuditActorType,
    BusinessAuditLog,
)
from app.db.models.integration import (
    IntegrationProvider,
)
from app.repositories.base import (
    TenantScopedRepository,
)


class BusinessAuditLogRepository(TenantScopedRepository):
    def add_conversation_claim(
        self,
        *,
        conversation_id: UUID,
        employee_id: UUID,
        actor_id: str,
        trace_id: str,
    ) -> BusinessAuditLog:
        return self.add_event(
            actor_type=BusinessAuditActorType.HUMAN,
            actor_id=actor_id,
            action="conversation.claimed",
            resource_type="conversation",
            resource_id=str(conversation_id),
            before_json={
                "state": "queued",
                "responsible_employee_id": None,
            },
            after_json={
                "state": "claimed",
                "responsible_employee_id": str(employee_id),
            },
            trace_id=trace_id,
        )

    def add_system_conversation_assignment_change(
        self,
        *,
        conversation_id: UUID,
        action: str,
        before_json: dict[str, object],
        after_json: dict[str, object],
        trace_id: str,
    ) -> BusinessAuditLog:
        return self.add_event(
            actor_type=BusinessAuditActorType.SYSTEM,
            actor_id="owner-unavailability-policy",
            action=action,
            resource_type="conversation",
            resource_id=str(conversation_id),
            before_json=before_json,
            after_json=after_json,
            trace_id=trace_id,
        )

    def add_integration_credentials_rotated(
        self,
        *,
        integration_id: UUID,
        provider: IntegrationProvider,
        actor_id: str,
        trace_id: str,
        previously_configured: bool,
    ) -> BusinessAuditLog:
        return self.add_event(
            actor_type=BusinessAuditActorType.HUMAN,
            actor_id=actor_id,
            action="integration.credentials_rotated",
            resource_type="integration",
            resource_id=str(integration_id),
            before_json={
                "provider": provider.value,
                "credentials_configured": (previously_configured),
            },
            after_json={
                "provider": provider.value,
                "credentials_configured": True,
            },
            trace_id=trace_id,
        )

    def add_outgoing_webhook_created(
        self,
        *,
        subscription_id: UUID,
        actor_id: str,
        trace_id: str,
        name: str,
        event_types: list[str],
    ) -> BusinessAuditLog:
        return self.add_event(
            actor_type=BusinessAuditActorType.HUMAN,
            actor_id=actor_id,
            action="webhook.subscription_created",
            resource_type=("outgoing_webhook_subscription"),
            resource_id=str(subscription_id),
            before_json=None,
            after_json={
                "name": name,
                "event_types": list(event_types),
                "active": True,
                "signing_secret_configured": True,
            },
            trace_id=trace_id,
        )

    def add_event(
        self,
        *,
        actor_type: BusinessAuditActorType,
        actor_id: str,
        action: str,
        resource_type: str,
        resource_id: str,
        before_json: dict[str, object] | None,
        after_json: dict[str, object] | None,
        trace_id: str,
    ) -> BusinessAuditLog:
        audit_log = BusinessAuditLog(
            tenant_id=self.tenant_id,
            actor_type=actor_type,
            actor_id=actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            before_json=sanitize_audit_payload(before_json),
            after_json=sanitize_audit_payload(after_json),
            trace_id=trace_id,
        )

        self._session.add(audit_log)

        return audit_log
