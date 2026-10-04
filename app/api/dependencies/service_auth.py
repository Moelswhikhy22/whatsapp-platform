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


async def require_service_principal(
    request: Request,
) -> ServicePrincipal:
    token = _extract_bearer_token(request)

    validator = get_service_token_validator()

    try:
        return await validator.validate(token)

    except MissingRequiredScopeError as exc:
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
        raise HTTPException(
            status_code=(status.HTTP_401_UNAUTHORIZED),
            detail=("Invalid bearer token."),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    except JwksUnavailableError as exc:
        raise HTTPException(
            status_code=(status.HTTP_503_SERVICE_UNAVAILABLE),
            detail=("Authentication service is unavailable."),
        ) from exc


def _extract_bearer_token(
    request: Request,
) -> str:
    authorization = request.headers.get("Authorization")

    if authorization is None:
        raise HTTPException(
            status_code=(status.HTTP_401_UNAUTHORIZED),
            detail=("Bearer token is required."),
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
