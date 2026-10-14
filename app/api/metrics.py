from __future__ import annotations

from fastapi import (
    APIRouter,
    Request,
)
from prometheus_client import (
    CONTENT_TYPE_LATEST,
)
from starlette.responses import Response

from app.observability.metrics import (
    render_latest_metrics,
)


router = APIRouter(
    tags=[
        "Observability",
    ],
)


@router.get(
    "/metrics",
    include_in_schema=False,
)
async def metrics(
    request: Request,
) -> Response:
    collector = getattr(
        request.app.state,
        "rabbitmq_queue_collector",
        None,
    )

    if collector is not None:
        # RabbitMQ monitoring failure must
        # not make the Prometheus endpoint
        # itself unavailable.
        await collector.collect()

    return Response(
        content=render_latest_metrics(),
        headers={
            "Content-Type": (CONTENT_TYPE_LATEST),
            "Cache-Control": "no-store",
        },
    )
