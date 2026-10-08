from __future__ import annotations

import io
import json
import logging
from uuid import uuid4

from app.observability.context import (
    bind_log_context,
    get_log_context,
    reset_log_context,
)
from app.observability.logging import (
    JsonLogFormatter,
    configure_json_logging,
    sanitize_log_text,
)


def _record(
    message: str,
    *,
    level: int = logging.INFO,
) -> logging.LogRecord:
    return logging.LogRecord(
        name="whatsapp-platform",
        level=level,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=(),
        exc_info=None,
    )


def test_log_context_defaults_empty() -> None:
    context = get_log_context()

    assert context.trace_id is None
    assert context.tenant_id is None


def test_log_context_binds_and_resets() -> None:
    tenant_id = uuid4()

    tokens = bind_log_context(
        trace_id="trace-123",
        tenant_id=tenant_id,
    )

    try:
        context = get_log_context()

        assert context.trace_id == "trace-123"

        assert context.tenant_id == str(tenant_id)

    finally:
        reset_log_context(tokens)

    restored = get_log_context()

    assert restored.trace_id is None
    assert restored.tenant_id is None


def test_formatter_outputs_valid_json() -> None:
    payload = json.loads(JsonLogFormatter().format(_record("hello world")))

    assert payload["message"] == "hello world"

    assert payload["level"] == "INFO"

    assert payload["logger"] == "whatsapp-platform"

    assert payload["timestamp"].endswith("Z")


def test_formatter_includes_trace_and_tenant_context() -> None:
    tenant_id = uuid4()

    tokens = bind_log_context(
        trace_id="trace-456",
        tenant_id=tenant_id,
    )

    try:
        payload = json.loads(JsonLogFormatter().format(_record("request processed")))
    finally:
        reset_log_context(tokens)

    assert payload["trace_id"] == "trace-456"

    assert payload["tenant_id"] == str(tenant_id)


def test_bearer_token_is_redacted() -> None:
    sanitized = sanitize_log_text("Authorization: Bearer super-secret-token")

    assert "super-secret-token" not in sanitized

    assert sanitized == "Authorization: [REDACTED]"


def test_sensitive_assignments_are_redacted() -> None:
    sanitized = sanitize_log_text("access_token=abc password=hunter2 api_key='secret-key'")

    assert "abc" not in sanitized
    assert "hunter2" not in sanitized
    assert "secret-key" not in sanitized

    assert sanitized.count("[REDACTED]") == 3


def test_url_password_is_redacted() -> None:
    sanitized = sanitize_log_text("database=postgresql://user:secret@example.com/db")

    assert "secret@example.com" not in sanitized

    assert "user:[REDACTED]@" in sanitized


def test_presigned_signature_is_redacted() -> None:
    sanitized = sanitize_log_text("url=https://s3.example/file?X-Amz-Signature=secret123")

    assert "secret123" not in sanitized

    assert "X-Amz-Signature=[REDACTED]" in sanitized


def test_formatter_allows_safe_structured_fields() -> None:
    record = _record("request finished")

    record.event = "http.request"
    record.method = "GET"
    record.path = "/api/v1/messages"
    record.status_code = 200
    record.duration_ms = 12.5

    payload = json.loads(JsonLogFormatter().format(record))

    assert payload["event"] == "http.request"

    assert payload["method"] == "GET"

    assert payload["path"] == "/api/v1/messages"

    assert payload["status_code"] == 200

    assert payload["duration_ms"] == 12.5


def test_exception_logs_type_without_exception_message() -> None:
    try:
        raise RuntimeError("secret-password")
    except RuntimeError:
        import sys

        exc_info = sys.exc_info()

    record = logging.LogRecord(
        name="whatsapp-platform",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="operation failed",
        args=(),
        exc_info=exc_info,
    )

    payload = json.loads(JsonLogFormatter().format(record))

    assert payload["exception"] == {"type": "RuntimeError"}

    assert "secret-password" not in json.dumps(payload)


def test_configure_json_logging_writes_json() -> None:
    stream = io.StringIO()

    configure_json_logging(
        level=logging.INFO,
        stream=stream,
    )

    logger = logging.getLogger("observability-test")

    logger.info(
        "service started",
        extra={
            "event": "service.started",
            "component": "api",
        },
    )

    payload = json.loads(stream.getvalue())

    assert payload["event"] == "service.started"

    assert payload["component"] == "api"
