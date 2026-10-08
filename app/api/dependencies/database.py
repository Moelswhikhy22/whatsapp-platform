from __future__ import annotations

from collections.abc import AsyncIterator
from typing import cast

from fastapi import Request
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
)


def get_session_factory(
    request: Request,
) -> async_sessionmaker[AsyncSession]:
    session_factory = getattr(
        request.app.state,
        "session_factory",
        None,
    )

    if session_factory is None:
        raise RuntimeError(
            "Database session factory is not initialized.",
        )

    return cast(
        async_sessionmaker[AsyncSession],
        session_factory,
    )


async def get_db_session(
    request: Request,
) -> AsyncIterator[AsyncSession]:
    session_factory = get_session_factory(request)

    async with session_factory() as session:
        yield session
