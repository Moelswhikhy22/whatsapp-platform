from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast

from app.db.models.message import MessageStatus


class MetaStatusPayloadError(ValueError):
    """Raised when a Meta message-status payload is malformed."""


class UnsupportedMetaStatusError(MetaStatusPayloadError):
    """Raised for a provider status not supported by V1."""


@dataclass(frozen=True, slots=True)
class ParsedMetaMessageStatus:
    meta_message_id: str
    status: MessageStatus
    meta_timestamp: datetime | None


def parse_meta_message_statuses(
    payload: dict[str, object],
) -> list[ParsedMetaMessageStatus]:
    parsed: list[ParsedMetaMessageStatus] = []

    entries = payload.get("entry")

    if not isinstance(entries, list):
        return parsed

    for raw_entry in entries:
        if not isinstance(raw_entry, dict):
            continue

        entry = cast(
            dict[str, object],
            raw_entry,
        )

        changes = entry.get("changes")

        if not isinstance(changes, list):
            continue

        for raw_change in changes:
            if not isinstance(
                raw_change,
                dict,
            ):
                continue

            change = cast(
                dict[str, object],
                raw_change,
            )

            raw_value = change.get("value")

            if not isinstance(
                raw_value,
                dict,
            ):
                continue

            value = cast(
                dict[str, object],
                raw_value,
            )

            raw_statuses = value.get("statuses")

            if not isinstance(
                raw_statuses,
                list,
            ):
                continue

            for raw_status in raw_statuses:
                if not isinstance(
                    raw_status,
                    dict,
                ):
                    raise MetaStatusPayloadError(("Meta message status must be an object."))

                status_payload = cast(
                    dict[str, object],
                    raw_status,
                )

                parsed.append(_parse_status(status_payload))

    return parsed


def _parse_status(
    payload: dict[str, object],
) -> ParsedMetaMessageStatus:
    raw_message_id = payload.get("id")

    if not isinstance(raw_message_id, str) or not raw_message_id:
        raise MetaStatusPayloadError("Meta status message ID is missing.")

    raw_status = payload.get("status")

    if not isinstance(raw_status, str) or not raw_status:
        raise MetaStatusPayloadError("Meta message status is missing.")

    try:
        status = MessageStatus(raw_status)
    except ValueError as exc:
        raise UnsupportedMetaStatusError(
            (f"Unsupported Meta message status: {raw_status}")
        ) from exc

    return ParsedMetaMessageStatus(
        meta_message_id=raw_message_id,
        status=status,
        meta_timestamp=_parse_timestamp(payload.get("timestamp")),
    )


def _parse_timestamp(
    raw_timestamp: object,
) -> datetime | None:
    if raw_timestamp is None:
        return None

    if not isinstance(
        raw_timestamp,
        (str, int),
    ):
        raise MetaStatusPayloadError("Meta status timestamp is invalid.")

    try:
        timestamp = int(raw_timestamp)
    except ValueError as exc:
        raise MetaStatusPayloadError("Meta status timestamp is invalid.") from exc

    try:
        return datetime.fromtimestamp(
            timestamp,
            tz=UTC,
        )
    except (
        OverflowError,
        OSError,
        ValueError,
    ) as exc:
        raise MetaStatusPayloadError("Meta status timestamp is invalid.") from exc
