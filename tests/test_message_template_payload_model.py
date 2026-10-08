from __future__ import annotations

from uuid import uuid4

from app.db.models.message_template_payload import (
    MessageTemplatePayload,
)


def test_message_template_payload_keeps_runtime_components() -> None:
    tenant_id = uuid4()
    message_id = uuid4()
    template_id = uuid4()

    components = [
        {
            "type": "body",
            "parameters": [
                {
                    "type": "text",
                    "text": "Ahmed",
                }
            ],
        }
    ]

    payload = MessageTemplatePayload(
        id=uuid4(),
        tenant_id=tenant_id,
        message_id=message_id,
        template_id=template_id,
        components_json=components,
    )

    assert payload.tenant_id == tenant_id
    assert payload.message_id == message_id
    assert payload.template_id == template_id
    assert payload.components_json == components
