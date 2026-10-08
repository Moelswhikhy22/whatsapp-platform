from __future__ import annotations

from app.db.models.message import (
    MessageType,
)
from app.integrations.meta.message_parser import (
    parse_meta_inbound_messages,
)


def test_document_message_extracts_media_descriptor() -> None:
    payload: dict[str, object] = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "metadata": {
                                "phone_number_id": ("123456"),
                            },
                            "contacts": [
                                {
                                    "wa_id": ("201000000000"),
                                    "profile": {
                                        "name": "Ahmed",
                                    },
                                }
                            ],
                            "messages": [
                                {
                                    "id": ("wamid.123"),
                                    "from": ("201000000000"),
                                    "timestamp": ("1791882000"),
                                    "type": ("document"),
                                    "document": {
                                        "id": ("media-123"),
                                        "mime_type": ("application/pdf"),
                                        "filename": ("invoice.pdf"),
                                        "caption": ("Invoice"),
                                    },
                                }
                            ],
                        }
                    }
                ]
            }
        ]
    }

    messages = parse_meta_inbound_messages(payload)

    assert len(messages) == 1

    message = messages[0]

    assert message.message_type is MessageType.DOCUMENT

    assert message.body_text == ("Invoice")

    assert message.media is not None

    assert message.media.provider_media_id == "media-123"

    assert message.media.webhook_mime_type == "application/pdf"

    assert message.media.original_filename == "invoice.pdf"
