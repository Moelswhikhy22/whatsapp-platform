from __future__ import annotations

from fastapi import (
    HTTPException,
    Request,
    status,
)

from app.api.dependencies.redis import get_redis
from app.auth.config import (
    load_session_cookie_config,
)
from app.auth.id_token import HumanPrincipal
from app.auth.session_cookie import (
    SESSION_COOKIE_NAME,
)
from app.auth.session_store import (
    RedisSessionStore,
    SessionRecord,
    SessionStorageError,
)
from app.db.models.security_access_log import (
    SecurityAccessOutcome,
    SecurityPrincipalType,
)
from app.security_access import (
    record_security_access,
)


async def require_authenticated_session(
    request: Request,
) -> SessionRecord:
    session_id = request.cookies.get(SESSION_COOKIE_NAME)

    if not session_id:
        await record_security_access(
            request=request,
            principal_type=(SecurityPrincipalType.ANONYMOUS),
            principal_id=None,
            event=("human.session_authentication"),
            outcome=(SecurityAccessOutcome.DENIED),
            reason_code=("missing_session_cookie"),
        )

        raise HTTPException(
            status_code=(status.HTTP_401_UNAUTHORIZED),
            detail="Authentication is required.",
        )

    cookie_config = load_session_cookie_config()

    session_store = RedisSessionStore(
        redis=get_redis(request),
        ttl_seconds=(cookie_config.max_age_seconds),
    )

    try:
        session = await session_store.get(
            session_id=session_id,
        )

    except SessionStorageError as exc:
        await record_security_access(
            request=request,
            principal_type=(SecurityPrincipalType.ANONYMOUS),
            principal_id=None,
            event=("human.session_authentication"),
            outcome=(SecurityAccessOutcome.FAILURE),
            reason_code=("session_store_unavailable"),
        )

        raise HTTPException(
            status_code=(status.HTTP_503_SERVICE_UNAVAILABLE),
            detail=("Session service is unavailable."),
        ) from exc

    if session is None:
        await record_security_access(
            request=request,
            principal_type=(SecurityPrincipalType.ANONYMOUS),
            principal_id=None,
            event=("human.session_authentication"),
            outcome=(SecurityAccessOutcome.DENIED),
            reason_code=("invalid_or_expired_session"),
        )

        raise HTTPException(
            status_code=(status.HTTP_401_UNAUTHORIZED),
            detail=("Session is invalid or expired."),
        )

    if session.status != "authenticated":
        await record_security_access(
            request=request,
            principal_type=(SecurityPrincipalType.ANONYMOUS),
            principal_id=None,
            event=("human.session_authentication"),
            outcome=(SecurityAccessOutcome.DENIED),
            reason_code=("session_not_authenticated"),
        )

        raise HTTPException(
            status_code=(status.HTTP_401_UNAUTHORIZED),
            detail=("Session is not authenticated."),
        )

    if session.subject is None or not session.subject.strip():
        await record_security_access(
            request=request,
            principal_type=(SecurityPrincipalType.ANONYMOUS),
            principal_id=None,
            event=("human.session_authentication"),
            outcome=(SecurityAccessOutcome.DENIED),
            reason_code=("invalid_session_identity"),
        )

        raise HTTPException(
            status_code=(status.HTTP_401_UNAUTHORIZED),
            detail=("Session identity is invalid."),
        )

    await record_security_access(
        request=request,
        principal_type=(SecurityPrincipalType.HUMAN),
        principal_id=session.subject,
        event=("human.session_authentication"),
        outcome=(SecurityAccessOutcome.SUCCESS),
    )

    return session


async def require_human_principal(
    request: Request,
) -> HumanPrincipal:
    session = await require_authenticated_session(request)

    subject = session.subject

    if subject is None:
        raise HTTPException(
            status_code=(status.HTTP_401_UNAUTHORIZED),
            detail=("Session identity is invalid."),
        )

    return HumanPrincipal(
        subject=subject,
    )
