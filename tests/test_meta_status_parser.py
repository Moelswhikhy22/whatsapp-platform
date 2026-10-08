from datetime import UTC, datetime

import pytest

from app.db.models.message import (
    MessageStatus,
)
from app.integrations.meta.status_parser import (
    UnsupportedMetaStatusError,
    parse_meta_message_statuses,
)


def _payload(
    *,
    status: str,
) -> dict[str, object]:
    return {
        "entry": [
            {
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "statuses": [
                                {
                                    "id": ("wamid.123"),
                                    "status": status,
                                    "timestamp": ("1791800000"),
                                }
                            ]
                        },
                    }
                ]
            }
        ]
    }


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "sent",
            MessageStatus.SENT,
        ),
        (
            "delivered",
            MessageStatus.DELIVERED,
        ),
        (
            "read",
            MessageStatus.READ,
        ),
        (
            "failed",
            MessageStatus.FAILED,
        ),
    ],
)
def test_parse_supported_status(
    raw: str,
    expected: MessageStatus,
) -> None:
    result = parse_meta_message_statuses(_payload(status=raw))

    assert len(result) == 1

    parsed = result[0]

    assert parsed.meta_message_id == "wamid.123"

    assert parsed.status is expected

    assert parsed.meta_timestamp == (
        datetime.fromtimestamp(
            1791800000,
            tz=UTC,
        )
    )


def test_message_only_payload_has_no_statuses() -> None:
    result = parse_meta_message_statuses(
        {"entry": [{"changes": [{"value": {"messages": [{"id": ("wamid.1")}]}}]}]}
    )

    assert result == []


def test_unsupported_status_is_rejected() -> None:
    with pytest.raises(UnsupportedMetaStatusError):
        parse_meta_message_statuses(_payload(status="unknown"))
