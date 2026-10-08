from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from app.repositories.conversation_search import (
    ConversationSearchFilters,
    ConversationSearchRepository,
)
from app.tenants.context import (
    TenantContext,
    TenantContextSource,
)


def _tenant_context(
    tenant_id: UUID,
) -> TenantContext:
    return TenantContext(
        tenant_id=tenant_id,
        slug=f"tenant-{tenant_id}",
        source=(TenantContextSource.AUTHENTICATED_SESSION),
    )


def _session_with_empty_result() -> AsyncMock:
    session = AsyncMock(spec=AsyncSession)

    result = MagicMock()
    result.all.return_value = []

    session.execute.return_value = result

    return session


def _captured_statement(
    session: AsyncMock,
) -> Select:
    return session.execute.await_args.args[0]


def _compiled_sql(
    statement: Select,
) -> tuple[str, dict[str, object]]:
    compiled = statement.compile(
        dialect=postgresql.dialect(),
    )

    return (
        str(compiled),
        dict(compiled.params),
    )


def _params_contain_uuid(
    params: dict[str, object],
    expected: UUID,
) -> bool:
    return any(value == expected for value in params.values())


def _params_contain_uuid_set(
    params: dict[str, object],
    expected: frozenset[UUID],
) -> bool:
    for value in params.values():
        if isinstance(
            value,
            (list, tuple, set, frozenset),
        ):
            if set(value) == set(expected):
                return True

    return False


@pytest.mark.asyncio
async def test_search_sql_always_contains_tenant_scope() -> None:
    tenant_a = uuid4()
    tenant_b_conversation_id = uuid4()

    session = _session_with_empty_result()

    repository = ConversationSearchRepository(
        session=session,
        tenant=_tenant_context(tenant_a),
    )

    await repository.search(
        filters=ConversationSearchFilters(conversation_id=(tenant_b_conversation_id)),
        allowed_group_ids=None,
        limit=50,
        offset=0,
    )

    statement = _captured_statement(session)

    sql, params = _compiled_sql(statement)

    assert "conversations.tenant_id" in sql

    assert "conversations.id" in sql

    assert _params_contain_uuid(
        params,
        tenant_a,
    )

    assert _params_contain_uuid(
        params,
        tenant_b_conversation_id,
    )


@pytest.mark.asyncio
async def test_group_admin_sql_is_limited_to_allowed_groups() -> None:
    tenant_id = uuid4()

    group_a = uuid4()
    group_b = uuid4()

    allowed_groups = frozenset(
        {
            group_a,
            group_b,
        }
    )

    session = _session_with_empty_result()

    repository = ConversationSearchRepository(
        session=session,
        tenant=_tenant_context(tenant_id),
    )

    await repository.search(
        filters=ConversationSearchFilters(),
        allowed_group_ids=(allowed_groups),
        limit=100,
        offset=0,
    )

    statement = _captured_statement(session)

    sql, params = _compiled_sql(statement)

    assert "conversations.tenant_id" in sql

    assert "conversations.group_id" in sql

    assert " IN " in sql

    assert _params_contain_uuid(
        params,
        tenant_id,
    )

    assert _params_contain_uuid_set(
        params,
        allowed_groups,
    )


@pytest.mark.asyncio
async def test_group_admin_with_no_administered_groups_gets_false_sql_scope() -> None:
    tenant_id = uuid4()

    session = _session_with_empty_result()

    repository = ConversationSearchRepository(
        session=session,
        tenant=_tenant_context(tenant_id),
    )

    await repository.search(
        filters=ConversationSearchFilters(),
        allowed_group_ids=frozenset(),
        limit=50,
        offset=0,
    )

    statement = _captured_statement(session)

    sql, _params = _compiled_sql(statement)

    # An admin with zero administered groups must
    # receive a query that cannot return any rows.
    #
    # SQLAlchemy may constant-fold:
    #
    #   tenant_id = :tenant_id AND false
    #
    # into:
    #
    #   false
    #
    # so the tenant bind parameter may disappear
    # from the compiled statement.
    assert "false" in sql.lower()
