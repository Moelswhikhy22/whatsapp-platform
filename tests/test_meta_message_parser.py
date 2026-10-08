from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.db.models.message import MessageType
from app.integrations.meta.message_parser import (
    UnsupportedMetaMessageTypeError,
    normalize_meta_phone,
    parse_meta_inbound_messages,
)


def _payload(
    message: dict[str, object],
) -> dict[str, object]:
    return {
        "entry": [
            {
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "metadata": {
                                "phone_number_id": ("meta-number-1"),
                            },
                            "contacts": [
                                {
                                    "wa_id": ("201234567890"),
                                    "profile": {
                                        "name": ("Ahmed"),
                                    },
                                }
                            ],
                            "messages": [message],
                        },
                    }
                ],
            }
        ]
    }


def test_parse_text_message() -> None:
    result = parse_meta_inbound_messages(
        _payload(
            {
                "id": "wamid.1",
                "from": "201234567890",
                "timestamp": "1791800000",
                "type": "text",
                "text": {
                    "body": "Hello",
                },
            }
        )
    )

    assert len(result) == 1

    message = result[0]

    assert message.meta_message_id == "wamid.1"

    assert message.meta_phone_number_id == "meta-number-1"

    assert message.normalized_sender_phone == "201234567890"

    assert message.sender_phone == "+201234567890"

    assert message.display_name == "Ahmed"

    assert message.message_type is MessageType.TEXT

    assert message.body_text == "Hello"

    assert message.meta_timestamp == (
        datetime.fromtimestamp(
            1791800000,
            tz=UTC,
        )
    )


def test_parse_media_caption() -> None:
    result = parse_meta_inbound_messages(
        _payload(
            {
                "id": "wamid.2",
                "from": "201234567890",
                "type": "image",
                "image": {
                    "id": "media-1",
                    "caption": "Invoice",
                },
            }
        )
    )

    assert len(result) == 1

    assert result[0].message_type is MessageType.IMAGE

    assert result[0].body_text == "Invoice"


def test_status_only_payload_has_no_messages() -> None:
    result = parse_meta_inbound_messages(
        {
            "entry": [
                {
                    "changes": [
                        {
                            "field": "messages",
                            "value": {
                                "statuses": [
                                    {
                                        "id": ("wamid.1"),
                                        "status": ("delivered"),
                                    }
                                ]
                            },
                        }
                    ]
                }
            ]
        }
    )

    assert result == []


def test_unsupported_message_type_is_rejected() -> None:
    with pytest.raises(UnsupportedMetaMessageTypeError):
        parse_meta_inbound_messages(
            _payload(
                {
                    "id": "wamid.3",
                    "from": "201234567890",
                    "type": "sticker",
                }
            )
        )


def test_normalize_meta_phone() -> None:
    assert normalize_meta_phone("+20 123-456-7890") == "201234567890"
