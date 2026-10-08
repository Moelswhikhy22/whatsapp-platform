from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.auth import (
    router as auth_router,
)
from app.api.health import (
    router as health_router,
)
from app.api.metrics import (
    router as metrics_router,
)
from app.api.v1.router import api_router
from app.core.redis import (
    create_redis_client,
)
from app.db.session import (
    create_database_engine,
    create_session_factory,
)
from app.middleware.request_observability import (
    request_observability_middleware,
)
from app.middleware.session_rate_limit import (
    HumanSessionRateLimitMiddleware,
)


@asynccontextmanager
async def lifespan(
    application: FastAPI,
) -> AsyncIterator[None]:
    database_engine = create_database_engine(
        os.environ["DATABASE_URL"],
    )

    session_factory = create_session_factory(
        database_engine,
    )

    redis = create_redis_client(
        os.environ["REDIS_URL"],
    )

    application.state.database_engine = database_engine

    application.state.session_factory = session_factory

    application.state.redis = redis

    try:
        yield

    finally:
        await redis.aclose()

        await database_engine.dispose()

        application.state.redis = None

        application.state.session_factory = None

        application.state.database_engine = None


def create_app() -> FastAPI:
    application = FastAPI(
        title=("WhatsApp Platform API"),
        version="0.1.0",
        lifespan=lifespan,
    )

    application.add_middleware(
        HumanSessionRateLimitMiddleware,
    )

    application.middleware("http")(request_observability_middleware)

    application.include_router(metrics_router)

    application.include_router(health_router)

    application.include_router(auth_router)

    application.include_router(
        api_router,
        prefix="/api/v1",
    )

    return application


app = create_app()
