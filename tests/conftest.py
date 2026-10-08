from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.session import (
    create_database_engine,
    create_session_factory,
)


def _test_database_url() -> str:
    database_url = os.getenv("TEST_DATABASE_URL")

    if database_url is None or not database_url.strip():
        pytest.skip(
            "TEST_DATABASE_URL is required for integration tests.",
        )

    return database_url


@pytest.fixture
async def integration_engine() -> AsyncIterator[AsyncEngine]:
    engine = create_database_engine(
        _test_database_url(),
    )

    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
async def integration_session(
    integration_engine: AsyncEngine,
) -> AsyncIterator[AsyncSession]:
    session_factory = create_session_factory(
        integration_engine,
    )

    async with session_factory() as session:
        try:
            yield session
        finally:
            await session.rollback()
