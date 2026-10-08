from __future__ import annotations

import secrets
from secrets import compare_digest
from urllib.parse import quote, urlencode

from fastapi import APIRouter, Request, Response, status
from fastapi.responses import JSONResponse, RedirectResponse

from app.api.dependencies.redis import get_redis
from app.auth.config import (
    load_auth_login_config,
    load_session_cookie_config,
    load_token_exchange_config,
)
from app.auth.id_token import (
    IdTokenJwksUnavailableError,
    InvalidIdTokenError,
    get_id_token_validator,
)
from app.auth.pkce import (
    create_code_challenge,
    generate_code_verifier,
)
from app.auth.session_cookie import (
    SESSION_COOKIE_NAME,
    delete_session_cookie,
    generate_session_id,
    set_session_cookie,
)
from app.auth.session_store import (
    RedisSessionStore,
    SessionRecord,
    SessionStorageError,
)
from app.auth.token_exchange import (
    InvalidTokenResponseError,
    TokenExchangeRejectedError,
    TokenExchangeUnavailableError,
    exchange_authorization_code,
)

router = APIRouter(
    prefix="/auth",
    tags=["authentication"],
)

_STATE_COOKIE = "wp_oauth_state"
_PKCE_COOKIE = "wp_oauth_pkce_verifier"
_NONCE_COOKIE = "wp_oauth_nonce"


def _set_transaction_cookie(
    response: RedirectResponse,
    *,
    key: str,
    value: str,
    max_age: int,
    secure: bool,
) -> None:
    response.set_cookie(
        key=key,
        value=value,
        max_age=max_age,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/auth",
    )


def _delete_transaction_cookies(
    response: Response,
    *,
    secure: bool,
) -> None:
    for key in (
        _STATE_COOKIE,
        _PKCE_COOKIE,
        _NONCE_COOKIE,
    ):
        response.delete_cookie(
            key=key,
            path="/auth",
            secure=secure,
            httponly=True,
            samesite="lax",
        )


def _callback_response(
    *,
    status_code: int,
    detail: str,
    secure: bool,
) -> JSONResponse:
    response = JSONResponse(
        status_code=status_code,
        content={
            "detail": detail,
        },
    )

    _delete_transaction_cookies(
        response,
        secure=secure,
    )

    response.headers["Cache-Control"] = "no-store"

    return response


def _successful_login_response(
    *,
    session_id: str,
    session_cookie_secure: bool,
    session_max_age: int,
    transaction_cookie_secure: bool,
) -> JSONResponse:
    response = JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "detail": "Authentication successful.",
        },
    )

    _delete_transaction_cookies(
        response,
        secure=transaction_cookie_secure,
    )

    set_session_cookie(
        response,
        session_id=session_id,
        secure=session_cookie_secure,
        max_age=session_max_age,
    )

    response.headers["Cache-Control"] = "no-store"

    return response


def _successful_logout_response(
    *,
    session_cookie_secure: bool,
    transaction_cookie_secure: bool,
) -> Response:
    response = Response(
        status_code=status.HTTP_204_NO_CONTENT,
    )

    delete_session_cookie(
        response,
        secure=session_cookie_secure,
    )

    _delete_transaction_cookies(
        response,
        secure=transaction_cookie_secure,
    )

    response.headers["Cache-Control"] = "no-store"

    return response


@router.get("/login")
async def login() -> RedirectResponse:
    config = load_auth_login_config()

    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)

    code_verifier = generate_code_verifier()
    code_challenge = create_code_challenge(code_verifier)

    realm = quote(
        config.keycloak_realm,
        safe="",
    )

    authorization_endpoint = (
        f"{config.keycloak_public_url}/realms/{realm}/protocol/openid-connect/auth"
    )

    query = urlencode(
        {
            "client_id": config.client_id,
            "response_type": "code",
            "scope": "openid profile email",
            "redirect_uri": config.redirect_uri,
            "state": state,
            "nonce": nonce,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
    )

    response = RedirectResponse(
        url=f"{authorization_endpoint}?{query}",
        status_code=status.HTTP_302_FOUND,
    )

    _set_transaction_cookie(
        response,
        key=_STATE_COOKIE,
        value=state,
        max_age=config.transaction_ttl_seconds,
        secure=config.transaction_cookie_secure,
    )

    _set_transaction_cookie(
        response,
        key=_PKCE_COOKIE,
        value=code_verifier,
        max_age=config.transaction_ttl_seconds,
        secure=config.transaction_cookie_secure,
    )

    _set_transaction_cookie(
        response,
        key=_NONCE_COOKIE,
        value=nonce,
        max_age=config.transaction_ttl_seconds,
        secure=config.transaction_cookie_secure,
    )

    response.headers["Cache-Control"] = "no-store"

    return response


@router.get("/callback")
async def callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> JSONResponse:
    config = load_auth_login_config()

    expected_state = request.cookies.get(_STATE_COOKIE)

    code_verifier = request.cookies.get(_PKCE_COOKIE)

    nonce = request.cookies.get(_NONCE_COOKIE)

    if expected_state is None or code_verifier is None or nonce is None:
        return _callback_response(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=("Authentication transaction is missing or expired."),
            secure=config.transaction_cookie_secure,
        )

    if state is None or not compare_digest(
        state,
        expected_state,
    ):
        return _callback_response(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid authentication state.",
            secure=config.transaction_cookie_secure,
        )

    if error is not None:
        return _callback_response(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Authorization was not completed.",
            secure=config.transaction_cookie_secure,
        )

    if code is None or not code:
        return _callback_response(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Authorization code is missing.",
            secure=config.transaction_cookie_secure,
        )

    exchange_config = load_token_exchange_config()

    try:
        token_set = await exchange_authorization_code(
            config=exchange_config,
            code=code,
            code_verifier=code_verifier,
        )

    except TokenExchangeRejectedError:
        return _callback_response(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Authorization code exchange failed.",
            secure=config.transaction_cookie_secure,
        )

    except (
        TokenExchangeUnavailableError,
        InvalidTokenResponseError,
    ):
        return _callback_response(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Identity provider exchange failed.",
            secure=config.transaction_cookie_secure,
        )

    validator = get_id_token_validator()

    try:
        principal = await validator.validate(
            token=token_set.id_token,
            expected_nonce=nonce,
        )

    except InvalidIdTokenError:
        return _callback_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Identity token validation failed.",
            secure=config.transaction_cookie_secure,
        )

    except IdTokenJwksUnavailableError:
        return _callback_response(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service is unavailable.",
            secure=config.transaction_cookie_secure,
        )

    session_cookie_config = load_session_cookie_config()

    session_id = generate_session_id()

    redis = get_redis(request)

    session_store = RedisSessionStore(
        redis=redis,
        ttl_seconds=(session_cookie_config.max_age_seconds),
    )

    session_record = SessionRecord(
        status="authenticated",
        access_token=token_set.access_token,
        id_token=token_set.id_token,
        refresh_token=token_set.refresh_token,
        token_type=token_set.token_type,
        expires_in=token_set.expires_in,
        refresh_expires_in=(token_set.refresh_expires_in),
        scope=token_set.scope,
        nonce=nonce,
        subject=principal.subject,
    )

    try:
        await session_store.create(
            session_id=session_id,
            record=session_record,
        )

    except SessionStorageError:
        return _callback_response(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Session service is unavailable.",
            secure=config.transaction_cookie_secure,
        )

    return _successful_login_response(
        session_id=session_id,
        session_cookie_secure=(session_cookie_config.secure),
        session_max_age=(session_cookie_config.max_age_seconds),
        transaction_cookie_secure=(config.transaction_cookie_secure),
    )


@router.post("/logout")
async def logout(
    request: Request,
) -> Response:
    auth_config = load_auth_login_config()
    session_cookie_config = load_session_cookie_config()

    session_id = request.cookies.get(SESSION_COOKIE_NAME)

    if not session_id:
        return _successful_logout_response(
            session_cookie_secure=(session_cookie_config.secure),
            transaction_cookie_secure=(auth_config.transaction_cookie_secure),
        )

    redis = get_redis(request)

    session_store = RedisSessionStore(
        redis=redis,
        ttl_seconds=(session_cookie_config.max_age_seconds),
    )

    try:
        await session_store.delete(
            session_id=session_id,
        )

    except SessionStorageError:
        response = JSONResponse(
            status_code=(status.HTTP_503_SERVICE_UNAVAILABLE),
            content={"detail": ("Session service is unavailable.")},
        )

        response.headers["Cache-Control"] = "no-store"

        return response

    return _successful_logout_response(
        session_cookie_secure=(session_cookie_config.secure),
        transaction_cookie_secure=(auth_config.transaction_cookie_secure),
    )
