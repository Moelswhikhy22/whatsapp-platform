from unittest.mock import MagicMock
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit_payload import (
    REDACTED_AUDIT_VALUE,
)
from app.db.models.business_audit_log import (
    BusinessAuditActorType,
)
from app.repositories.business_audit_log import (
    BusinessAuditLogRepository,
)
from app.tenants.context import (
    TenantContext,
    TenantContextSource,
)


def test_business_audit_repository_redacts_nested_secrets() -> None:
    tenant_id = uuid4()

    tenant = TenantContext(
        tenant_id=tenant_id,
        slug="audit-test",
        source=(TenantContextSource.AUTHENTICATED_SESSION),
    )

    session = MagicMock(
        spec=AsyncSession,
    )

    repository = BusinessAuditLogRepository(
        session=session,
        tenant=tenant,
    )

    resource_id = uuid4()

    audit_log = repository.add_event(
        actor_type=BusinessAuditActorType.HUMAN,
        actor_id="user-1",
        action="integration.updated",
        resource_type="integration",
        resource_id=str(resource_id),
        before_json={
            "config": {
                "client_secret": "do-not-store",
                "provider": "meta",
            }
        },
        after_json={
            "config": {
                "client_secret": "new-secret",
                "provider": "meta",
            }
        },
        trace_id="trace-business-1",
    )

    assert audit_log.tenant_id == tenant_id

    before = audit_log.before_json

    assert before is not None

    config = before["config"]

    assert isinstance(config, dict)

    assert config["client_secret"] == REDACTED_AUDIT_VALUE

    assert config["provider"] == "meta"

    session.add.assert_called_once_with(audit_log)
def test_outgoing_webhook_created_audit_contains_no_secret() -> None:
    tenant_id = uuid4()

    tenant = TenantContext(
        tenant_id=tenant_id,
        slug="audit-webhook-test",
        source=(
            TenantContextSource.AUTHENTICATED_SESSION
        ),
    )

    session = MagicMock(
        spec=AsyncSession,
    )

    repository = BusinessAuditLogRepository(
        session=session,
        tenant=tenant,
    )

    subscription_id = uuid4()

    audit = (
        repository
        .add_outgoing_webhook_created(
            subscription_id=subscription_id,
            actor_id="tenant-admin",
            trace_id="trace-webhook-create",
            name="ERP Hook",
            event_types=[
                "message.received",
                "message.sent",
            ],
        )
    )

    assert audit.action == (
        "webhook.subscription_created"
    )

    assert audit.resource_type == (
        "outgoing_webhook_subscription"
    )

    assert audit.resource_id == str(
        subscription_id
    )

    assert audit.before_json is None

    assert audit.after_json == {
        "name": "ERP Hook",
        "event_types": [
            "message.received",
            "message.sent",
        ],
        "active": True,
        "signing_secret_configured": True,
    }

    serialized = str(
        audit.after_json
    ).lower()

    assert (
        "signing_secret_configured"
        in serialized
    )

    assert ("s" * 32) not in serialized
    assert "access_token" not in serialized
    assert "client_secret" not in serialized
    assert "password" not in serialized