from __future__ import annotations

from uuid import UUID

from app.services.media_object_key import (
    MediaObjectKeyBuilder,
)


TENANT_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

CONVERSATION_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")

MESSAGE_ID = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

MEDIA_ID = UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")


def test_production_media_key_uses_prod_prefix() -> None:
    builder = MediaObjectKeyBuilder(environment="production")

    assert builder.build(
        tenant_id=TENANT_ID,
        conversation_id=(CONVERSATION_ID),
        message_id=MESSAGE_ID,
        media_id=MEDIA_ID,
    ) == (f"prod/{TENANT_ID}/whatsapp/{CONVERSATION_ID}/{MESSAGE_ID}/{MEDIA_ID}")


def test_local_media_key_is_tenant_prefixed() -> None:
    builder = MediaObjectKeyBuilder(environment="local")

    result = builder.build(
        tenant_id=TENANT_ID,
        conversation_id=(CONVERSATION_ID),
        message_id=MESSAGE_ID,
        media_id=MEDIA_ID,
    )

    assert result.startswith(f"local/{TENANT_ID}/whatsapp/")
