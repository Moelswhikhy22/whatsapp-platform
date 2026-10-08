from __future__ import annotations

from fastapi import (
    HTTPException,
    Request,
    status,
)

from app.auth.service_token import (
    InvalidServiceTokenError,
    JwksUnavailableError,
    MissingRequiredScopeError,
    ServicePrincipal,
    get_service_token_validator,
)
from app.db.models.security_access_log import (
    SecurityAccessOutcome,
    SecurityPrincipalType,
)
from app.security_access import (
    record_security_access,
)


async def require_service_principal(
    request: Request,
) -> ServicePrincipal:
    try:
        token = _extract_bearer_token(request)

    except HTTPException:
        authorization = request.headers.get("Authorization")

        reason_code = (
            "missing_bearer_token" if authorization is None else "invalid_authorization_header"
        )

        await record_security_access(
            request=request,
            principal_type=(SecurityPrincipalType.ANONYMOUS),
            principal_id=None,
            event=("service.token_authentication"),
            outcome=(SecurityAccessOutcome.DENIED),
            reason_code=reason_code,
        )

        raise

    validator = get_service_token_validator()

    try:
        principal = await validator.validate(token)

    except MissingRequiredScopeError as exc:
        # The validator did not return a trusted
        # ServicePrincipal, so do not infer or
        # reconstruct an integration identity.
        await record_security_access(
            request=request,
            principal_type=(SecurityPrincipalType.ANONYMOUS),
            principal_id=None,
            event=("service.token_authentication"),
            outcome=(SecurityAccessOutcome.DENIED),
            reason_code=("missing_required_scope"),
        )

        raise HTTPException(
            status_code=(status.HTTP_403_FORBIDDEN),
            detail=("Required service scope is missing."),
            headers={
                "WWW-Authenticate": (
                    f'Bearer error="insufficient_scope", scope="{exc.required_scope}"'
                )
            },
        ) from exc

    except InvalidServiceTokenError as exc:
        await record_security_access(
            request=request,
            principal_type=(SecurityPrincipalType.ANONYMOUS),
            principal_id=None,
            event=("service.token_authentication"),
            outcome=(SecurityAccessOutcome.DENIED),
            reason_code=("invalid_bearer_token"),
        )

        raise HTTPException(
            status_code=(status.HTTP_401_UNAUTHORIZED),
            detail="Invalid bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    except JwksUnavailableError as exc:
        await record_security_access(
            request=request,
            principal_type=(SecurityPrincipalType.ANONYMOUS),
            principal_id=None,
            event=("service.token_authentication"),
            outcome=(SecurityAccessOutcome.FAILURE),
            reason_code=("jwks_unavailable"),
        )

        raise HTTPException(
            status_code=(status.HTTP_503_SERVICE_UNAVAILABLE),
            detail=("Authentication service is unavailable."),
        ) from exc

    await record_security_access(
        request=request,
        principal_type=(SecurityPrincipalType.INTEGRATION),
        principal_id=principal.client_id,
        event=("service.token_authentication"),
        outcome=(SecurityAccessOutcome.SUCCESS),
    )

    return principal


def _extract_bearer_token(
    request: Request,
) -> str:
    authorization = request.headers.get("Authorization")

    if authorization is None:
        raise HTTPException(
            status_code=(status.HTTP_401_UNAUTHORIZED),
            detail="Bearer token is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    scheme, separator, credentials = authorization.partition(" ")

    token = credentials.strip()

    if not separator or scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=(status.HTTP_401_UNAUTHORIZED),
            detail=("Invalid authorization header."),
            headers={"WWW-Authenticate": "Bearer"},
        )

    return token
