from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache


_INVALID_FILENAME_CHARACTERS = re.compile(r'[<>:"/\\|?*]+')

_REPEATED_WHITESPACE = re.compile(r"\s+")

_WINDOWS_RESERVED_FILENAMES = frozenset(
    {
        "con",
        "prn",
        "aux",
        "nul",
        *(f"com{index}" for index in range(1, 10)),
        *(f"lpt{index}" for index in range(1, 10)),
    }
)

_DEFAULT_FILENAME = "media"
_MAX_FILENAME_LENGTH = 180

_DEFAULT_MAX_SIZE_BYTES = 100_000_000

_DEFAULT_ALLOWED_MIME_TYPES = frozenset(
    {
        "image/jpeg",
        "image/png",
        "audio/aac",
        "audio/amr",
        "audio/mpeg",
        "audio/mp4",
        "audio/ogg",
        "video/mp4",
        "video/3gpp",
        "text/plain",
        "text/csv",
        "application/pdf",
        "application/rtf",
        "application/msword",
        "application/vnd.ms-excel",
        "application/vnd.ms-powerpoint",
        ("application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ("application/vnd.openxmlformats-officedocument.presentationml.presentation"),
    }
)


class MediaSecurityError(ValueError):
    def __init__(
        self,
        *,
        code: str,
        message: str,
    ) -> None:
        super().__init__(message)

        self.code = code


class MediaSecurityConfigurationError(RuntimeError):
    pass


class MediaSizeInvalidError(MediaSecurityError):
    def __init__(self) -> None:
        super().__init__(
            code="MEDIA_SIZE_INVALID",
            message=("Media size must be greater than zero."),
        )


class MediaSizeLimitExceededError(MediaSecurityError):
    def __init__(
        self,
        *,
        size_bytes: int,
        max_size_bytes: int,
    ) -> None:
        super().__init__(
            code="MEDIA_SIZE_LIMIT_EXCEEDED",
            message=(f"Media size exceeds the configured limit of {max_size_bytes} bytes."),
        )

        self.size_bytes = size_bytes
        self.max_size_bytes = max_size_bytes


class MediaMimeTypeInvalidError(MediaSecurityError):
    def __init__(self) -> None:
        super().__init__(
            code="MEDIA_MIME_TYPE_INVALID",
            message=("Media MIME type is invalid."),
        )


class MediaMimeTypeNotAllowedError(MediaSecurityError):
    def __init__(
        self,
        *,
        mime_type: str,
    ) -> None:
        super().__init__(
            code="MEDIA_MIME_TYPE_NOT_ALLOWED",
            message=("Media MIME type is not allowed."),
        )

        self.mime_type = mime_type


@dataclass(
    frozen=True,
    slots=True,
)
class MediaSecurityPolicy:
    max_size_bytes: int
    allowed_mime_types: frozenset[str]

    def __post_init__(
        self,
    ) -> None:
        if self.max_size_bytes <= 0:
            raise ValueError("max_size_bytes must be greater than zero.")

        if not self.allowed_mime_types:
            raise ValueError("allowed_mime_types must not be empty.")

        normalized_types = frozenset(
            normalize_mime_type(mime_type) for mime_type in self.allowed_mime_types
        )

        object.__setattr__(
            self,
            "allowed_mime_types",
            normalized_types,
        )


@dataclass(
    frozen=True,
    slots=True,
)
class ValidatedMediaMetadata:
    original_filename: str | None
    mime_type: str
    size_bytes: int


@lru_cache(maxsize=1)
def load_media_security_policy() -> MediaSecurityPolicy:
    max_size_bytes = _positive_int_env(
        "MEDIA_MAX_SIZE_BYTES",
        default=_DEFAULT_MAX_SIZE_BYTES,
    )

    raw_allowed_types = os.getenv("MEDIA_ALLOWED_MIME_TYPES")

    if raw_allowed_types is None:
        allowed_types = _DEFAULT_ALLOWED_MIME_TYPES
    else:
        allowed_types = frozenset(
            item.strip() for item in raw_allowed_types.split(",") if item.strip()
        )

        if not allowed_types:
            raise (
                MediaSecurityConfigurationError(
                    "MEDIA_ALLOWED_MIME_TYPES must contain at least one MIME type."
                )
            )

    try:
        return MediaSecurityPolicy(
            max_size_bytes=max_size_bytes,
            allowed_mime_types=allowed_types,
        )
    except ValueError as exc:
        raise (MediaSecurityConfigurationError("Media security configuration is invalid.")) from exc


def sanitize_filename(
    value: str | None,
    *,
    fallback: str = _DEFAULT_FILENAME,
    max_length: int = (_MAX_FILENAME_LENGTH),
) -> str:
    if max_length <= 0:
        raise ValueError("max_length must be greater than zero.")

    normalized_fallback = _sanitize_filename_component(
        fallback,
    )

    if not normalized_fallback:
        normalized_fallback = _DEFAULT_FILENAME

    if value is None:
        return _truncate_filename(
            normalized_fallback,
            max_length=max_length,
        )

    normalized = unicodedata.normalize(
        "NFKC",
        value,
    )

    normalized = normalized.replace(
        "\\",
        "/",
    )

    normalized = normalized.rsplit(
        "/",
        maxsplit=1,
    )[-1]

    normalized = _sanitize_filename_component(normalized)

    if not normalized or normalized in {".", ".."}:
        normalized = normalized_fallback

    stem = normalized.split(
        ".",
        maxsplit=1,
    )[0].casefold()

    if stem in _WINDOWS_RESERVED_FILENAMES:
        normalized = f"_{normalized}"

    return _truncate_filename(
        normalized,
        max_length=max_length,
    )


def normalize_mime_type(
    value: str,
) -> str:
    normalized = (
        value.split(
            ";",
            maxsplit=1,
        )[0]
        .strip()
        .lower()
    )

    if not normalized or "/" not in normalized:
        raise MediaMimeTypeInvalidError

    type_name, subtype = normalized.split(
        "/",
        maxsplit=1,
    )

    if not type_name or not subtype or "*" in type_name or "*" in subtype:
        raise MediaMimeTypeInvalidError

    if any(
        character.isspace() or unicodedata.category(character).startswith("C")
        for character in normalized
    ):
        raise MediaMimeTypeInvalidError

    return normalized


def validate_media_metadata(
    *,
    original_filename: str | None,
    mime_type: str,
    size_bytes: int,
    policy: MediaSecurityPolicy,
) -> ValidatedMediaMetadata:
    if size_bytes <= 0:
        raise MediaSizeInvalidError

    if size_bytes > policy.max_size_bytes:
        raise (
            MediaSizeLimitExceededError(
                size_bytes=size_bytes,
                max_size_bytes=(policy.max_size_bytes),
            )
        )

    normalized_mime_type = normalize_mime_type(mime_type)

    if normalized_mime_type not in policy.allowed_mime_types:
        raise (
            MediaMimeTypeNotAllowedError(
                mime_type=(normalized_mime_type),
            )
        )

    safe_filename = None if original_filename is None else sanitize_filename(original_filename)

    return ValidatedMediaMetadata(
        original_filename=safe_filename,
        mime_type=normalized_mime_type,
        size_bytes=size_bytes,
    )


def _positive_int_env(
    name: str,
    *,
    default: int,
) -> int:
    raw_value = os.getenv(name)

    if raw_value is None:
        return default

    normalized = raw_value.strip()

    try:
        value = int(normalized)
    except ValueError as exc:
        raise (MediaSecurityConfigurationError(f"{name} must be an integer.")) from exc

    if value <= 0:
        raise (MediaSecurityConfigurationError(f"{name} must be greater than zero."))

    return value


def _sanitize_filename_component(
    value: str,
) -> str:
    normalized = unicodedata.normalize(
        "NFKC",
        value,
    )

    normalized = "".join(
        character for character in normalized if not unicodedata.category(character).startswith("C")
    )

    normalized = _INVALID_FILENAME_CHARACTERS.sub(
        "_",
        normalized,
    )

    normalized = _REPEATED_WHITESPACE.sub(
        " ",
        normalized,
    )

    return normalized.strip(" .")


def _truncate_filename(
    value: str,
    *,
    max_length: int,
) -> str:
    if len(value) <= max_length:
        return value

    if "." not in value:
        return value[:max_length]

    stem, extension = value.rsplit(
        ".",
        maxsplit=1,
    )

    if not stem or not extension:
        return value[:max_length]

    suffix = f".{extension}"

    if len(suffix) >= max_length:
        return value[:max_length]

    allowed_stem_length = max_length - len(suffix)

    return stem[:allowed_stem_length] + suffix
