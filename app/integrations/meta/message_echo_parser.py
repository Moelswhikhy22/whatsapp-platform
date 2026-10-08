from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast

from app.db.models.message import MessageType
from app.integrations.meta.message_parser import (
    normalize_meta_phone,
)


class MetaMessageEchoPayloadError(ValueError):
    """Raised when a Meta message echo payload is malformed."""


class UnsupportedMetaMessageEchoTypeError(MetaMessageEchoPayloadError):
    """Raised when an external WhatsApp echo type is unsupported."""


@dataclass(frozen=True, slots=True)
class ParsedMetaMessageEcho:
    meta_message_id: str
    meta_phone_number_id: str
    business_phone: str
    normalized_business_phone: str
    recipient_phone: str
    normalized_recipient_phone: str
    message_type: MessageType
    body_text: str | None
    meta_timestamp: datetime | None


def parse_meta_message_echoes(
    payload: dict[str, object],
) -> list[ParsedMetaMessageEcho]:
    result: list[ParsedMetaMessageEcho] = []

    entries = payload.get("entry")

    if not isinstance(entries, list):
        return result

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
            if not isinstance(raw_change, dict):
                continue

            change = cast(
                dict[str, object],
                raw_change,
            )

            if change.get("field") != "smb_message_echoes":
                continue

            raw_value = change.get("value")

            if not isinstance(raw_value, dict):
                raise MetaMessageEchoPayloadError("Meta message echo value is missing.")

            value = cast(
                dict[str, object],
                raw_value,
            )

            phone_number_id = _phone_number_id(value)

            raw_echoes = value.get("message_echoes")

            if not isinstance(raw_echoes, list):
                continue

            for raw_echo in raw_echoes:
                if not isinstance(raw_echo, dict):
                    raise MetaMessageEchoPayloadError("Meta message echo must be an object.")

                echo = cast(
                    dict[str, object],
                    raw_echo,
                )

                result.append(
                    _parse_echo(
                        echo=echo,
                        meta_phone_number_id=phone_number_id,
                    )
                )

    return result


def _phone_number_id(
    value: dict[str, object],
) -> str:
    raw_metadata = value.get("metadata")

    if not isinstance(raw_metadata, dict):
        raise MetaMessageEchoPayloadError("Meta message echo metadata is missing.")

    metadata = cast(
        dict[str, object],
        raw_metadata,
    )

    phone_number_id = metadata.get("phone_number_id")

    if not isinstance(phone_number_id, str) or not phone_number_id.strip():
        raise MetaMessageEchoPayloadError("Meta message echo phone_number_id is missing.")

    return phone_number_id.strip()


def _parse_echo(
    *,
    echo: dict[str, object],
    meta_phone_number_id: str,
) -> ParsedMetaMessageEcho:
    raw_id = echo.get("id")

    if not isinstance(raw_id, str) or not raw_id.strip():
        raise MetaMessageEchoPayloadError("Meta message echo ID is missing.")

    raw_from = echo.get("from")

    if not isinstance(raw_from, str) or not raw_from.strip():
        raise MetaMessageEchoPayloadError("Meta message echo sender is missing.")

    raw_to = echo.get("to")

    if not isinstance(raw_to, str) or not raw_to.strip():
        raise MetaMessageEchoPayloadError("Meta message echo recipient is missing.")

    normalized_business_phone = normalize_meta_phone(raw_from)

    normalized_recipient_phone = normalize_meta_phone(raw_to)

    raw_type = echo.get("type")

    if not isinstance(raw_type, str) or not raw_type.strip():
        raise MetaMessageEchoPayloadError("Meta message echo type is missing.")

    try:
        message_type = MessageType(raw_type)
    except ValueError as exc:
        raise UnsupportedMetaMessageEchoTypeError(
            f"Unsupported Meta message echo type: {raw_type}"
        ) from exc

    return ParsedMetaMessageEcho(
        meta_message_id=raw_id.strip(),
        meta_phone_number_id=meta_phone_number_id,
        business_phone=f"+{normalized_business_phone}",
        normalized_business_phone=(normalized_business_phone),
        recipient_phone=f"+{normalized_recipient_phone}",
        normalized_recipient_phone=(normalized_recipient_phone),
        message_type=message_type,
        body_text=_extract_body_text(
            echo,
            message_type,
        ),
        meta_timestamp=_parse_timestamp(echo.get("timestamp")),
    )


def _extract_body_text(
    echo: dict[str, object],
    message_type: MessageType,
) -> str | None:
    raw_content = echo.get(message_type.value)

    if message_type is MessageType.TEXT:
        if not isinstance(raw_content, dict):
            raise MetaMessageEchoPayloadError("Meta message echo text payload is missing.")

        content = cast(
            dict[str, object],
            raw_content,
        )

        body = content.get("body")

        if not isinstance(body, str):
            raise MetaMessageEchoPayloadError("Meta message echo text body is missing.")

        return body

    if not isinstance(raw_content, dict):
        return None

    content = cast(
        dict[str, object],
        raw_content,
    )

    caption = content.get("caption")

    if isinstance(caption, str):
        return caption

    return None


def _parse_timestamp(
    value: object,
) -> datetime | None:
    if value is None:
        return None

    if isinstance(value, bool):
        raise MetaMessageEchoPayloadError("Meta message echo timestamp is invalid.")

    try:
        timestamp = int(value)
    except (TypeError, ValueError) as exc:
        raise MetaMessageEchoPayloadError("Meta message echo timestamp is invalid.") from exc

    try:
        return datetime.fromtimestamp(
            timestamp,
            tz=UTC,
        )
    except (OverflowError, OSError, ValueError) as exc:
        raise MetaMessageEchoPayloadError("Meta message echo timestamp is invalid.") from exc
