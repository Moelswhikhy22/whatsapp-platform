from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit_payload import (
    REDACTED_AUDIT_VALUE,
)
from app.db.models.business_audit_log import (
    BusinessAuditActorType,
)
from app.repositories.template import (
    TemplateRepository,
)


def test_template_audit_redacts_sensitive_payload_values() -> None:
    tenant_id = uuid4()
    template_id = uuid4()

    session = MagicMock(
        spec=AsyncSession,
    )

    repository = TemplateRepository(
        session=session,
        tenant_id=tenant_id,
    )

    audit = repository.add_template_audit(
        template_id=template_id,
        actor_id="user-123",
        action="template.updated",
        before={
            "name": "welcome",
            "config": {
                "client_secret": "must-not-leak",
                "language": "en",
            },
        },
        after={
            "name": "welcome-v2",
            "config": {
                "access_token": "must-not-leak",
                "language": "ar",
            },
        },
    )

    assert audit.tenant_id == tenant_id

    assert audit.actor_type is (BusinessAuditActorType.HUMAN)

    assert audit.actor_id == "user-123"
    assert audit.action == "template.updated"

    assert audit.resource_type == "template"
    assert audit.resource_id == str(template_id)

    assert audit.before_json is not None
    assert audit.after_json is not None

    before_config = audit.before_json["config"]

    assert isinstance(
        before_config,
        dict,
    )

    assert before_config["client_secret"] == (REDACTED_AUDIT_VALUE)

    assert before_config["language"] == "en"

    after_config = audit.after_json["config"]

    assert isinstance(
        after_config,
        dict,
    )

    assert after_config["access_token"] == (REDACTED_AUDIT_VALUE)

    assert after_config["language"] == "ar"

    session.add.assert_called_once_with(audit)
