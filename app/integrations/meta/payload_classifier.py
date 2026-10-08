from __future__ import annotations

from dataclasses import dataclass
from typing import cast


@dataclass(frozen=True, slots=True)
class MetaPayloadParts:
    has_messages: bool
    has_statuses: bool
    has_message_echoes: bool


def classify_meta_payload(
    payload: dict[str, object],
) -> MetaPayloadParts:
    has_messages = False
    has_statuses = False
    has_message_echoes = False

    entries = payload.get("entry")

    if not isinstance(entries, list):
        return MetaPayloadParts(
            has_messages=False,
            has_statuses=False,
            has_message_echoes=False,
        )

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

            messages = value.get("messages")

            if isinstance(messages, list) and messages:
                has_messages = True

            statuses = value.get("statuses")

            if isinstance(statuses, list) and statuses:
                has_statuses = True

            field = change.get("field")
            message_echoes = value.get("message_echoes")

            if (
                field == "smb_message_echoes"
                and isinstance(message_echoes, list)
                and message_echoes
            ):
                has_message_echoes = True

    return MetaPayloadParts(
        has_messages=has_messages,
        has_statuses=has_statuses,
        has_message_echoes=has_message_echoes,
    )
