from __future__ import annotations

import json
import logging
import re
import sys
from datetime import (
    UTC,
    datetime,
)
from typing import TextIO

from app.observability.context import (
    get_log_context,
)


_REDACTED = "[REDACTED]"


_BEARER_PATTERN = re.compile(
    r"\bBearer\s+[^\s,;]+",
    re.IGNORECASE,
)


_SENSITIVE_ASSIGNMENT_PATTERN = re.compile(
    r"""
    (?P<prefix>
        \b
        (?:
            access_token
            |refresh_token
            |id_token
            |client_secret
            |app_secret
            |verify_token
            |password
            |api_key
            |authorization
            |cookie
            |vault_token
            |presigned_url
            |x-amz-signature
            |x-amz-credential
            |x-amz-security-token
        )
        \s*
        [:=]
        \s*
    )
    (?P<value>
        "[^"]*"
        |
        '[^']*'
        |
        [^\s,&;]+
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)


_URL_CREDENTIAL_PATTERN = re.compile(
    r"""
    (?P<scheme>
        [a-z][a-z0-9+.-]*://
    )
    (?P<username>
        [^:/@\s]+
    )
    :
    (?P<password>
        [^@\s]+
    )
    @
    """,
    re.IGNORECASE | re.VERBOSE,
)


_SAFE_EXTRA_FIELDS = (
    "event",
    "component",
    "operation",
    "outcome",
    "provider",
    "queue",
    "method",
    "path",
    "status_code",
    "duration_ms",
    "resource_type",
    "resource_id",
)
_AUTHORIZATION_HEADER_PATTERN = re.compile(
    r"\bAuthorization\s*:\s*[^\r\n]+",
    re.IGNORECASE,
)


class JsonLogFormatter(logging.Formatter):
    def format(
        self,
        record: logging.LogRecord,
    ) -> str:
        context = get_log_context()

        payload: dict[
            str,
            object,
        ] = {
            "timestamp": (
                datetime.fromtimestamp(
                    record.created,
                    tz=UTC,
                )
                .isoformat(timespec="milliseconds")
                .replace(
                    "+00:00",
                    "Z",
                )
            ),
            "level": (record.levelname),
            "logger": record.name,
            "message": sanitize_log_text(record.getMessage()),
        }

        trace_id = context.trace_id or _safe_optional_string(
            getattr(
                record,
                "trace_id",
                None,
            )
        )

        tenant_id = context.tenant_id or _safe_optional_string(
            getattr(
                record,
                "tenant_id",
                None,
            )
        )

        if trace_id is not None:
            payload["trace_id"] = trace_id

        if tenant_id is not None:
            payload["tenant_id"] = tenant_id

        for field in _SAFE_EXTRA_FIELDS:
            value = getattr(
                record,
                field,
                None,
            )

            if value is None:
                continue

            payload[field] = _safe_log_value(value)

        if record.exc_info is not None:
            exception_type = record.exc_info[0]

            payload["exception"] = {
                "type": (exception_type.__name__ if exception_type is not None else "Exception")
            }

        return json.dumps(
            payload,
            ensure_ascii=False,
            separators=(
                ",",
                ":",
            ),
            sort_keys=True,
        )


def configure_json_logging(
    *,
    level: int | str = logging.INFO,
    stream: TextIO | None = None,
) -> None:
    handler = logging.StreamHandler(stream or sys.stdout)

    handler.setFormatter(JsonLogFormatter())

    root_logger = logging.getLogger()

    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level)


def sanitize_log_text(
    value: str,
) -> str:
    sanitized = _AUTHORIZATION_HEADER_PATTERN.sub(
        f"Authorization: {_REDACTED}",
        value,
    )

    sanitized = _BEARER_PATTERN.sub(
        f"Bearer {_REDACTED}",
        sanitized,
    )

    sanitized = _SENSITIVE_ASSIGNMENT_PATTERN.sub(
        _replace_sensitive_assignment,
        sanitized,
    )

    sanitized = _URL_CREDENTIAL_PATTERN.sub(
        _replace_url_credentials,
        sanitized,
    )

    return sanitized


def _replace_sensitive_assignment(
    match: re.Match[str],
) -> str:
    return f"{match.group('prefix')}{_REDACTED}"


def _replace_url_credentials(
    match: re.Match[str],
) -> str:
    return f"{match.group('scheme')}{match.group('username')}:{_REDACTED}@"


def _safe_optional_string(
    value: object,
) -> str | None:
    if value is None:
        return None

    normalized = str(value).strip()

    if not normalized:
        return None

    return sanitize_log_text(normalized)


def _safe_log_value(
    value: object,
) -> object:
    if isinstance(
        value,
        str,
    ):
        return sanitize_log_text(value)

    if isinstance(
        value,
        (
            int,
            float,
            bool,
        ),
    ):
        return value

    return sanitize_log_text(str(value))
