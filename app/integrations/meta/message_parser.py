from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast

from app.db.models.message import MessageType


class MetaInboundPayloadError(ValueError):
    """Raised when a Meta inbound message payload is malformed."""


class UnsupportedMetaMessageTypeError(MetaInboundPayloadError):
    """Raised when Meta sends a message type not supported by V1."""


_MEDIA_MESSAGE_TYPES = frozenset(
    {
        MessageType.IMAGE,
        MessageType.DOCUMENT,
        MessageType.AUDIO,
        MessageType.VIDEO,
    }
)


@dataclass(frozen=True, slots=True)
class ParsedMetaInboundMedia:
    provider_media_id: str
    webhook_mime_type: str | None = None
    original_filename: str | None = None


@dataclass(frozen=True, slots=True)
class ParsedMetaInboundMessage:
    meta_message_id: str
    meta_phone_number_id: str
    sender_phone: str
    normalized_sender_phone: str
    display_name: str | None
    message_type: MessageType
    body_text: str | None
    meta_timestamp: datetime | None
    media: ParsedMetaInboundMedia | None = None


def parse_meta_inbound_messages(
    payload: dict[str, object],
) -> list[ParsedMetaInboundMessage]:
    messages: list[ParsedMetaInboundMessage] = []

    entries = payload.get("entry")

    if not isinstance(entries, list):
        return messages

    for raw_entry in entries:
        if not isinstance(
            raw_entry,
            dict,
        ):
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

            raw_messages = value.get("messages")

            if not isinstance(
                raw_messages,
                list,
            ):
                continue

            phone_number_id = _phone_number_id(value)

            contact_names = _contact_names(value)

            for raw_message in raw_messages:
                if not isinstance(
                    raw_message,
                    dict,
                ):
                    raise (MetaInboundPayloadError(("Meta message must be an object.")))

                message = cast(
                    dict[str, object],
                    raw_message,
                )

                messages.append(
                    _parse_message(
                        message=message,
                        meta_phone_number_id=(phone_number_id),
                        contact_names=(contact_names),
                    )
                )

    return messages


def _phone_number_id(
    value: dict[str, object],
) -> str:
    raw_metadata = value.get("metadata")

    if not isinstance(
        raw_metadata,
        dict,
    ):
        raise MetaInboundPayloadError(("Meta message metadata is missing."))

    metadata = cast(
        dict[str, object],
        raw_metadata,
    )

    phone_number_id = metadata.get("phone_number_id")

    if (
        not isinstance(
            phone_number_id,
            str,
        )
        or not phone_number_id.strip()
    ):
        raise MetaInboundPayloadError(("Meta phone_number_id is missing."))

    return phone_number_id.strip()


def _contact_names(
    value: dict[str, object],
) -> dict[str, str]:
    result: dict[str, str] = {}

    contacts = value.get("contacts")

    if not isinstance(
        contacts,
        list,
    ):
        return result

    for raw_contact in contacts:
        if not isinstance(
            raw_contact,
            dict,
        ):
            continue

        contact = cast(
            dict[str, object],
            raw_contact,
        )

        wa_id = contact.get("wa_id")

        if (
            not isinstance(
                wa_id,
                str,
            )
            or not wa_id
        ):
            continue

        raw_profile = contact.get("profile")

        if not isinstance(
            raw_profile,
            dict,
        ):
            continue

        profile = cast(
            dict[str, object],
            raw_profile,
        )

        name = profile.get("name")

        if isinstance(name, str) and name.strip():
            result[wa_id] = name.strip()

    return result


def _parse_message(
    *,
    message: dict[str, object],
    meta_phone_number_id: str,
    contact_names: dict[str, str],
) -> ParsedMetaInboundMessage:
    raw_id = message.get("id")

    if not isinstance(raw_id, str) or not raw_id:
        raise MetaInboundPayloadError("Meta message ID is missing.")

    raw_sender = message.get("from")

    if (
        not isinstance(
            raw_sender,
            str,
        )
        or not raw_sender
    ):
        raise MetaInboundPayloadError(("Meta message sender is missing."))

    normalized_sender = normalize_meta_phone(raw_sender)

    raw_type = message.get("type")

    if (
        not isinstance(
            raw_type,
            str,
        )
        or not raw_type
    ):
        raise MetaInboundPayloadError(("Meta message type is missing."))

    try:
        message_type = MessageType(raw_type)
    except ValueError as exc:
        raise (
            UnsupportedMetaMessageTypeError((f"Unsupported Meta message type: {raw_type}"))
        ) from exc

    body_text = _extract_body_text(
        message,
        message_type,
    )

    media = _extract_media(
        message,
        message_type,
    )

    return ParsedMetaInboundMessage(
        meta_message_id=raw_id,
        meta_phone_number_id=(meta_phone_number_id),
        sender_phone=(f"+{normalized_sender}"),
        normalized_sender_phone=(normalized_sender),
        display_name=(contact_names.get(raw_sender)),
        message_type=message_type,
        body_text=body_text,
        meta_timestamp=(_parse_timestamp(message.get("timestamp"))),
        media=media,
    )


def normalize_meta_phone(
    value: str,
) -> str:
    normalized = "".join(character for character in value if character.isdigit())

    if not normalized:
        raise MetaInboundPayloadError(("Meta sender phone number is invalid."))

    return normalized


def _extract_body_text(
    message: dict[str, object],
    message_type: MessageType,
) -> str | None:
    if message_type is MessageType.TEXT:
        raw_text = message.get("text")

        if not isinstance(
            raw_text,
            dict,
        ):
            raise MetaInboundPayloadError(("Meta text payload is missing."))

        text = cast(
            dict[str, object],
            raw_text,
        )

        body = text.get("body")

        if not isinstance(
            body,
            str,
        ):
            raise MetaInboundPayloadError(("Meta text body is missing."))

        return body

    if message_type in {
        MessageType.IMAGE,
        MessageType.DOCUMENT,
        MessageType.VIDEO,
    }:
        raw_media = message.get(message_type.value)

        if not isinstance(
            raw_media,
            dict,
        ):
            return None

        media = cast(
            dict[str, object],
            raw_media,
        )

        caption = media.get("caption")

        if isinstance(
            caption,
            str,
        ):
            return caption

    return None


def _extract_media(
    message: dict[str, object],
    message_type: MessageType,
) -> ParsedMetaInboundMedia | None:
    if message_type not in _MEDIA_MESSAGE_TYPES:
        return None

    raw_media = message.get(message_type.value)

    if not isinstance(
        raw_media,
        dict,
    ):
        raise MetaInboundPayloadError(("Meta media payload is missing."))

    media = cast(
        dict[str, object],
        raw_media,
    )

    raw_media_id = media.get("id")

    if (
        not isinstance(
            raw_media_id,
            str,
        )
        or not raw_media_id.strip()
    ):
        raise MetaInboundPayloadError(("Meta media ID is missing."))

    raw_mime_type = media.get("mime_type")

    mime_type: str | None = None

    if raw_mime_type is not None:
        if not isinstance(
            raw_mime_type,
            str,
        ):
            raise (MetaInboundPayloadError(("Meta media MIME type is invalid.")))

        normalized_mime = raw_mime_type.strip()

        if normalized_mime:
            mime_type = normalized_mime

    original_filename: str | None = None

    if message_type is MessageType.DOCUMENT:
        raw_filename = media.get("filename")

        if isinstance(
            raw_filename,
            str,
        ):
            normalized_filename = raw_filename.strip()

            if normalized_filename:
                original_filename = normalized_filename

    return ParsedMetaInboundMedia(
        provider_media_id=(raw_media_id.strip()),
        webhook_mime_type=mime_type,
        original_filename=(original_filename),
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
        raise MetaInboundPayloadError("Meta timestamp is invalid.")

    try:
        timestamp = int(raw_timestamp)
    except ValueError as exc:
        raise MetaInboundPayloadError("Meta timestamp is invalid.") from exc

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
        raise MetaInboundPayloadError("Meta timestamp is invalid.") from exc
