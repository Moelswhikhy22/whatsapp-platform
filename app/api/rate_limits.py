from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import (
    Depends,
    HTTPException,
    Request,
    status,
)

from app.api.dependencies.human_context import (
    HumanConversationRequestContext,
    require_human_conversation_request_context,
)
from app.api.dependencies.redis import get_redis
from app.db.models.security_access_log import (
    SecurityAccessOutcome,
    SecurityPrincipalType,
)
from app.rate_limit import (
    FixedWindowRateLimiter,
    RateLimitBackendUnavailableError,
)
from app.redis_keys import RedisKeys
from app.security_access import (
    record_security_access,
)


@dataclass(
    frozen=True,
    slots=True,
)
class RateLimitPolicy:
    bucket: str
    limit: int
    window_seconds: int


MESSAGE_SEND_RATE_LIMIT = RateLimitPolicy(
    bucket="message_send",
    limit=60,
    window_seconds=60,
)

MEDIA_URL_RATE_LIMIT = RateLimitPolicy(
    bucket="media_url",
    limit=120,
    window_seconds=60,
)

INTEGRATION_ADMIN_RATE_LIMIT = RateLimitPolicy(
    bucket="integration_admin",
    limit=10,
    window_seconds=60,
)


async def _enforce_human_tenant_policy(
    *,
    request: Request,
    request_context: HumanConversationRequestContext,
    policy: RateLimitPolicy,
) -> None:
    tenant_id = request_context.tenant.tenant_id
    principal_id = request_context.principal.subject

    key = RedisKeys.rate_limit(
        tenant_id=tenant_id,
        bucket=policy.bucket,
        identity=principal_id,
    )

    try:
        redis = get_redis(request)

        decision = await FixedWindowRateLimiter(redis).check(
            key=key,
            limit=policy.limit,
            window_seconds=(policy.window_seconds),
        )
    except (
        RateLimitBackendUnavailableError,
        RuntimeError,
    ) as exc:
        await record_security_access(
            request=request,
            principal_type=(SecurityPrincipalType.HUMAN),
            principal_id=principal_id,
            tenant_id=tenant_id,
            event="rate_limit.backend_failure",
            outcome=(SecurityAccessOutcome.FAILURE),
            resource_type="rate_limit",
            resource_id=policy.bucket,
            reason_code=("rate_limit_backend_unavailable"),
        )

        raise HTTPException(
            status_code=(status.HTTP_503_SERVICE_UNAVAILABLE),
            detail={
                "code": ("RATE_LIMIT_BACKEND_UNAVAILABLE"),
                "message": ("Request limiting service is unavailable."),
            },
        ) from exc

    if decision.allowed:
        return

    await record_security_access(
        request=request,
        principal_type=(SecurityPrincipalType.HUMAN),
        principal_id=principal_id,
        tenant_id=tenant_id,
        event="rate_limit.exceeded",
        outcome=SecurityAccessOutcome.DENIED,
        resource_type="rate_limit",
        resource_id=policy.bucket,
        reason_code="rate_limit_exceeded",
    )

    raise HTTPException(
        status_code=(status.HTTP_429_TOO_MANY_REQUESTS),
        detail={
            "code": "RATE_LIMIT_EXCEEDED",
            "message": ("Too many requests."),
        },
        headers={
            "Retry-After": str(decision.retry_after_seconds),
        },
    )


async def require_message_send_rate_limit(
    request: Request,
    request_context: Annotated[
        HumanConversationRequestContext,
        Depends(
            require_human_conversation_request_context,
        ),
    ],
) -> None:
    await _enforce_human_tenant_policy(
        request=request,
        request_context=request_context,
        policy=MESSAGE_SEND_RATE_LIMIT,
    )


async def require_media_url_rate_limit(
    request: Request,
    request_context: Annotated[
        HumanConversationRequestContext,
        Depends(
            require_human_conversation_request_context,
        ),
    ],
) -> None:
    await _enforce_human_tenant_policy(
        request=request,
        request_context=request_context,
        policy=MEDIA_URL_RATE_LIMIT,
    )


async def require_integration_admin_rate_limit(
    request: Request,
    request_context: Annotated[
        HumanConversationRequestContext,
        Depends(
            require_human_conversation_request_context,
        ),
    ],
) -> None:
    await _enforce_human_tenant_policy(
        request=request,
        request_context=request_context,
        policy=INTEGRATION_ADMIN_RATE_LIMIT,
    )
