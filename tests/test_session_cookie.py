from __future__ import annotations

from starlette.responses import Response

from app.auth.session_cookie import (
    SESSION_COOKIE_NAME,
    delete_session_cookie,
    generate_session_id,
    set_session_cookie,
)


def test_generate_session_id_is_random() -> None:
    first = generate_session_id()
    second = generate_session_id()

    assert first != second

    assert len(first) >= 43
    assert len(second) >= 43


def test_set_session_cookie_local() -> None:
    response = Response()

    set_session_cookie(
        response,
        session_id="test-session-id",
        secure=False,
        max_age=28_800,
    )

    header = response.headers["set-cookie"].lower()

    assert f"{SESSION_COOKIE_NAME}=test-session-id" in header

    assert "httponly" in header
    assert "samesite=lax" in header
    assert "max-age=28800" in header
    assert "path=/" in header

    assert "secure" not in header


def test_set_session_cookie_production_is_secure() -> None:
    response = Response()

    set_session_cookie(
        response,
        session_id="test-session-id",
        secure=True,
        max_age=28_800,
    )

    header = response.headers["set-cookie"].lower()

    assert "httponly" in header
    assert "secure" in header
    assert "samesite=lax" in header
    assert "path=/" in header


def test_session_cookie_does_not_expose_tokens() -> None:
    response = Response()

    set_session_cookie(
        response,
        session_id="opaque-session-id",
        secure=True,
        max_age=28_800,
    )

    header = response.headers["set-cookie"]

    assert "access_token" not in header
    assert "refresh_token" not in header
    assert "id_token" not in header

    assert "opaque-session-id" in header


def test_delete_session_cookie() -> None:
    response = Response()

    delete_session_cookie(
        response,
        secure=True,
    )

    header = response.headers["set-cookie"].lower()

    assert SESSION_COOKIE_NAME in header
    assert "max-age=0" in header
    assert "httponly" in header
    assert "secure" in header
    assert "samesite=lax" in header
    assert "path=/" in header
