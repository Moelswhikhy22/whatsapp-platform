from __future__ import annotations

from time import perf_counter
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Response,
    status,
)

from app.observability.metrics import (
    infrastructure_metrics,
)
from app.schemas.health import (
    DependencyHealthResponse,
    LivenessResponse,
    ReadinessResponse,
)
from app.services.health import (
    HealthChecker,
)


router = APIRouter(
    prefix="/health",
    tags=[
        "health",
    ],
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
    started_at = perf_counter()

    dependency_health = await health_checker.check()

    infrastructure_metrics.observe_dependency_health(
        postgres=(dependency_health.postgres),
        redis=(dependency_health.redis),
        rabbitmq=(dependency_health.rabbitmq),
    )

    dependencies = DependencyHealthResponse(
        postgres=("up" if dependency_health.postgres else "down"),
        redis=("up" if dependency_health.redis else "down"),
        rabbitmq=("up" if dependency_health.rabbitmq else "down"),
    )

    if not (dependency_health.required_dependencies_ready):
        readiness_status = "not_ready"

        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

        result = ReadinessResponse(
            status=readiness_status,
            dependencies=dependencies,
        )

    elif not (dependency_health.all_dependencies_ready):
        readiness_status = "degraded"

        result = ReadinessResponse(
            status=readiness_status,
            dependencies=dependencies,
        )

    else:
        readiness_status = "ready"

        result = ReadinessResponse(
            status=readiness_status,
            dependencies=dependencies,
        )

    infrastructure_metrics.observe_readiness(
        status=readiness_status,
        duration_seconds=max(
            perf_counter() - started_at,
            0.0,
        ),
    )

    return result
