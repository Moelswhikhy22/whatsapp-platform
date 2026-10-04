from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.auth import router as auth_router
from app.api.health import router as health_router
from app.api.v1.router import api_router
from app.core.redis import create_redis_client


@asynccontextmanager
async def lifespan(
    application: FastAPI,
) -> AsyncIterator[None]:
    redis = create_redis_client(os.environ["REDIS_URL"])

    application.state.redis = redis

    try:
        yield
    finally:
        await redis.aclose()

        application.state.redis = None


def create_app() -> FastAPI:
    application = FastAPI(
        title="WhatsApp Platform API",
        version="0.1.0",
        lifespan=lifespan,
    )

    application.include_router(health_router)

    application.include_router(auth_router)

    application.include_router(
        api_router,
        prefix="/api/v1",
    )

    return application


app = create_app()
