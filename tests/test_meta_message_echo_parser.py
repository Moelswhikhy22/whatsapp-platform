from datetime import UTC, datetime

import pytest

from app.db.models.message import MessageType
from app.integrations.meta.message_echo_parser import (
    UnsupportedMetaMessageEchoTypeError,
    parse_meta_message_echoes,
)


def _payload(
    *,
    message_type: str = "text",
) -> dict[str, object]:
    echo: dict[str, object] = {
        "from": "201000000000",
        "to": "201111111111",
        "id": "wamid.echo.1",
        "timestamp": "1760432400",
        "type": message_type,
    }

    if message_type == "text":
        echo["text"] = {"body": "Sent from WhatsApp Business App"}

    return {
        "entry": [
            {
                "changes": [
                    {
                        "field": "smb_message_echoes",
                        "value": {
                            "metadata": {
                                "phone_number_id": ("123456789"),
                            },
                            "message_echoes": [echo],
                        },
                    }
                ]
            }
        ]
    }


def test_parses_whatsapp_external_echo() -> None:
    result = parse_meta_message_echoes(_payload())

    assert len(result) == 1

    parsed = result[0]

    assert parsed.meta_message_id == ("wamid.echo.1")

    assert parsed.meta_phone_number_id == ("123456789")

    assert parsed.business_phone == ("+201000000000")

    assert parsed.normalized_business_phone == "201000000000"

    assert parsed.recipient_phone == ("+201111111111")

    assert parsed.normalized_recipient_phone == "201111111111"

    assert parsed.message_type is (MessageType.TEXT)

    assert parsed.body_text == ("Sent from WhatsApp Business App")

    assert parsed.meta_timestamp == (
        datetime.fromtimestamp(
            1760432400,
            tz=UTC,
        )
    )


def test_ignores_non_echo_change() -> None:
    result = parse_meta_message_echoes(
        {
            "entry": [
                {
                    "changes": [
                        {
                            "field": "messages",
                            "value": {"message_echoes": [{"id": ("wamid.echo.1")}]},
                        }
                    ]
                }
            ]
        }
    )

    assert result == []


def test_rejects_edit_until_supported() -> None:
    with pytest.raises(UnsupportedMetaMessageEchoTypeError):
        parse_meta_message_echoes(
            _payload(
                message_type="edit",
            )
        )


def test_rejects_revoke_until_supported() -> None:
    with pytest.raises(UnsupportedMetaMessageEchoTypeError):
        parse_meta_message_echoes(
            _payload(
                message_type="revoke",
            )
        )
