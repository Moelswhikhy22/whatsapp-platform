from __future__ import annotations

import pytest

from app.media_security import (
    MediaMimeTypeInvalidError,
    MediaMimeTypeNotAllowedError,
    MediaSecurityPolicy,
    MediaSizeInvalidError,
    MediaSizeLimitExceededError,
    normalize_mime_type,
    sanitize_filename,
    validate_media_metadata,
)


POLICY = MediaSecurityPolicy(
    max_size_bytes=10_000,
    allowed_mime_types=frozenset(
        {
            "image/jpeg",
            "image/png",
            "application/pdf",
            "audio/ogg",
            "video/mp4",
        }
    ),
)


def test_filename_removes_posix_path() -> None:
    assert sanitize_filename("../../etc/passwd") == "passwd"


def test_filename_removes_windows_path() -> None:
    assert sanitize_filename(r"..\..\secret\invoice.pdf") == "invoice.pdf"


def test_filename_removes_control_characters() -> None:
    assert sanitize_filename("invoice\x00\x01.pdf") == "invoice.pdf"


def test_filename_replaces_unsafe_characters() -> None:
    assert sanitize_filename('invoice<2026>:"Q4".pdf') == "invoice_2026_Q4_.pdf"


def test_filename_uses_fallback_when_blank() -> None:
    assert sanitize_filename("   ") == "media"


def test_filename_protects_windows_reserved_names() -> None:
    assert sanitize_filename("CON.txt") == "_CON.txt"


def test_filename_preserves_extension_when_truncated() -> None:
    filename = "a" * 300 + ".pdf"

    sanitized = sanitize_filename(
        filename,
        max_length=50,
    )

    assert len(sanitized) == 50
    assert sanitized.endswith(".pdf")


def test_mime_type_is_normalized() -> None:
    assert normalize_mime_type(" IMAGE/JPEG ; charset=binary ") == "image/jpeg"


@pytest.mark.parametrize(
    "value",
    [
        "",
        "image",
        "*/jpeg",
        "image/*",
        "image/ jpeg",
    ],
)
def test_invalid_mime_type_is_rejected(
    value: str,
) -> None:
    with pytest.raises(MediaMimeTypeInvalidError):
        normalize_mime_type(value)


def test_zero_size_media_is_rejected() -> None:
    with pytest.raises(MediaSizeInvalidError):
        validate_media_metadata(
            original_filename="file.pdf",
            mime_type="application/pdf",
            size_bytes=0,
            policy=POLICY,
        )


def test_negative_size_media_is_rejected() -> None:
    with pytest.raises(MediaSizeInvalidError):
        validate_media_metadata(
            original_filename="file.pdf",
            mime_type="application/pdf",
            size_bytes=-1,
            policy=POLICY,
        )


def test_oversized_media_is_rejected() -> None:
    with pytest.raises(MediaSizeLimitExceededError) as exc_info:
        validate_media_metadata(
            original_filename="file.pdf",
            mime_type="application/pdf",
            size_bytes=10_001,
            policy=POLICY,
        )

    assert exc_info.value.code == "MEDIA_SIZE_LIMIT_EXCEEDED"


def test_disallowed_mime_type_is_rejected() -> None:
    with pytest.raises(MediaMimeTypeNotAllowedError) as exc_info:
        validate_media_metadata(
            original_filename="payload.exe",
            mime_type=("application/octet-stream"),
            size_bytes=100,
            policy=POLICY,
        )

    assert exc_info.value.mime_type == "application/octet-stream"


def test_valid_media_is_normalized_and_sanitized() -> None:
    result = validate_media_metadata(
        original_filename=(r"C:\fakepath\invoice.pdf"),
        mime_type=("APPLICATION/PDF; charset=binary"),
        size_bytes=5_000,
        policy=POLICY,
    )

    assert result.original_filename == "invoice.pdf"

    assert result.mime_type == "application/pdf"

    assert result.size_bytes == 5_000


def test_policy_normalizes_allowed_mime_types() -> None:
    policy = MediaSecurityPolicy(
        max_size_bytes=100,
        allowed_mime_types=frozenset(
            {
                " IMAGE/JPEG ",
            }
        ),
    )

    assert policy.allowed_mime_types == frozenset(
        {
            "image/jpeg",
        }
    )


def test_policy_rejects_invalid_size_limit() -> None:
    with pytest.raises(ValueError):
        MediaSecurityPolicy(
            max_size_bytes=0,
            allowed_mime_types=frozenset(
                {
                    "image/jpeg",
                }
            ),
        )


def test_policy_requires_allowed_mime_types() -> None:
    with pytest.raises(ValueError):
        MediaSecurityPolicy(
            max_size_bytes=100,
            allowed_mime_types=frozenset(),
        )
