from __future__ import annotations

from unittest.mock import (
    AsyncMock,
    MagicMock,
    patch,
)

import pytest
from fastapi import Request

from app.db.models.security_access_log import (
    SecurityAccessOutcome,
    SecurityPrincipalType,
)
from app.security_access import (
    get_request_trace_id,
    record_security_access,
)


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/test",
            "query_string": (b"access_token=must-not-leak"),
            "headers": [
                (
                    b"user-agent",
                    b"pytest-agent",
                ),
                (
                    b"authorization",
                    b"Bearer must-not-leak",
                ),
                (
                    b"cookie",
                    b"session=must-not-leak",
                ),
            ],
            "client": (
                "127.0.0.1",
                50000,
            ),
            "server": (
                "testserver",
                80,
            ),
            "scheme": "http",
            "app": MagicMock(),
        }
    )


def test_request_trace_id_is_stable() -> None:
    request = _request()

    first = get_request_trace_id(request)

    second = get_request_trace_id(request)

    assert first == second
    assert first


@pytest.mark.asyncio
async def test_security_writer_excludes_sensitive_request_data() -> None:
    request = _request()

    repository = MagicMock()

    session = AsyncMock()

    session_context = AsyncMock()

    session_context.__aenter__.return_value = session

    session_context.__aexit__.return_value = None

    session_factory = MagicMock(return_value=session_context)

    with (
        patch(
            ("app.security_access.get_session_factory"),
            return_value=session_factory,
        ),
        patch(
            ("app.security_access.SecurityAccessLogRepository"),
            return_value=repository,
        ),
    ):
        await record_security_access(
            request=request,
            principal_type=(SecurityPrincipalType.ANONYMOUS),
            principal_id=None,
            event="authentication",
            outcome=(SecurityAccessOutcome.DENIED),
            reason_code=("missing_credentials"),
        )

    call = repository.add_event.call_args

    assert call.kwargs["request_path"] == "/api/v1/test"

    assert call.kwargs["request_method"] == "GET"

    assert call.kwargs["client_ip"] == "127.0.0.1"

    assert call.kwargs["user_agent"] == "pytest-agent"

    serialized = str(call.kwargs)

    assert "must-not-leak" not in serialized
    assert "authorization" not in serialized
    assert "cookie" not in serialized

    session.commit.assert_awaited_once()
