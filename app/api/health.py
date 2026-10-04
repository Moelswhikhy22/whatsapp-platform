from __future__ import annotations

from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Response,
    status,
)

from app.schemas.health import (
    DependencyHealthResponse,
    LivenessResponse,
    ReadinessResponse,
)
from app.services.health import HealthChecker

router = APIRouter(
    prefix="/health",
    tags=["health"],
)


def get_health_checker() -> HealthChecker:
    return HealthChecker.from_environment()


@router.get(
    "/live",
    response_model=LivenessResponse,
)
async def liveness() -> LivenessResponse:
    return LivenessResponse()


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": ReadinessResponse,
        },
    },
)
async def readiness(
    response: Response,
    health_checker: Annotated[
        HealthChecker,
        Depends(get_health_checker),
    ],
) -> ReadinessResponse:
    dependency_health = await health_checker.check()

    dependencies = DependencyHealthResponse(
        postgres=("up" if dependency_health.postgres else "down"),
        redis=("up" if dependency_health.redis else "down"),
        rabbitmq=("up" if dependency_health.rabbitmq else "down"),
    )

    if not dependency_health.required_dependencies_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

        return ReadinessResponse(
            status="not_ready",
            dependencies=dependencies,
        )

    if not dependency_health.all_dependencies_ready:
        return ReadinessResponse(
            status="degraded",
            dependencies=dependencies,
        )

    return ReadinessResponse(
        status="ready",
        dependencies=dependencies,
    )
