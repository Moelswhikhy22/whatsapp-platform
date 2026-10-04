from __future__ import annotations

import secrets

from starlette.responses import Response

SESSION_COOKIE_NAME = "wp_session"


def generate_session_id() -> str:
    return secrets.token_urlsafe(32)


def set_session_cookie(
    response: Response,
    *,
    session_id: str,
    secure: bool,
    max_age: int,
) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_id,
        max_age=max_age,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )


def delete_session_cookie(
    response: Response,
    *,
    secure: bool,
) -> None:
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        httponly=True,
        secure=secure,
        samesite="lax",
    )
