from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.message import (
    Message,
)
from app.repositories.message_status import (
    MessageStatusRepository,
)


@pytest.mark.asyncio
async def test_message_lookup_uses_tenant_scope_and_row_lock() -> None:
    tenant_id = uuid4()

    scalars = MagicMock()
    scalars.first.return_value = None

    session = MagicMock(spec=AsyncSession)

    session.scalars = AsyncMock(return_value=scalars)

    repository = MessageStatusRepository(
        session=session,
        tenant_id=tenant_id,
    )

    await repository.get_outbound_message_for_update("wamid.1")

    statement = session.scalars.await_args.args[0]

    sql = str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={
                "literal_binds": True,
            },
        )
    )

    assert "FOR UPDATE" in sql

    assert "messages.tenant_id" in sql
    assert "messages.meta_message_id" in sql
