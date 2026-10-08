from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.authorization.context import (
    AuthorizationContext,
)
from app.authorization.conversation import (
    ConversationActorContext,
)
from app.authorization.errors import (
    AuthorizationDeniedError,
)
from app.authorization.roles import Role
from app.repositories.conversation_search import (
    ConversationSearchFilters,
    ConversationSearchRepository,
)
from app.services.conversation_search import (
    ConversationSearchService,
)


@pytest.mark.asyncio
async def test_tenant_admin_searches_entire_tenant() -> None:
    tenant_id = uuid4()

    repository = AsyncMock(spec=ConversationSearchRepository)

    repository.search.return_value = []

    service = ConversationSearchService(repository)

    await service.search(
        context=AuthorizationContext(
            actor_id="tenant-admin",
            role=Role.TENANT_ADMIN,
            tenant_id=tenant_id,
        ),
        actor=ConversationActorContext(),
        filters=ConversationSearchFilters(),
        limit=50,
        offset=0,
    )

    repository.search.assert_awaited_once_with(
        filters=ConversationSearchFilters(),
        allowed_group_ids=None,
        limit=50,
        offset=0,
    )


@pytest.mark.asyncio
async def test_group_admin_search_is_scoped_to_administered_groups() -> None:
    tenant_id = uuid4()

    group_a = uuid4()
    group_b = uuid4()

    repository = AsyncMock(spec=ConversationSearchRepository)

    repository.search.return_value = []

    service = ConversationSearchService(repository)

    actor = ConversationActorContext(
        employee_id=uuid4(),
        administered_group_ids=(
            frozenset(
                {
                    group_a,
                    group_b,
                }
            )
        ),
    )

    await service.search(
        context=AuthorizationContext(
            actor_id="group-admin",
            role=Role.GROUP_ADMIN,
            tenant_id=tenant_id,
        ),
        actor=actor,
        filters=ConversationSearchFilters(),
        limit=100,
        offset=20,
    )

    repository.search.assert_awaited_once_with(
        filters=ConversationSearchFilters(),
        allowed_group_ids=(
            frozenset(
                {
                    group_a,
                    group_b,
                }
            )
        ),
        limit=100,
        offset=20,
    )


@pytest.mark.asyncio
async def test_employee_cannot_use_admin_search() -> None:
    tenant_id = uuid4()

    repository = AsyncMock(spec=ConversationSearchRepository)

    service = ConversationSearchService(repository)

    with pytest.raises(AuthorizationDeniedError):
        await service.search(
            context=AuthorizationContext(
                actor_id="employee",
                role=Role.EMPLOYEE,
                tenant_id=tenant_id,
            ),
            actor=(ConversationActorContext(employee_id=uuid4())),
            filters=(ConversationSearchFilters()),
            limit=50,
            offset=0,
        )

    repository.search.assert_not_awaited()


@pytest.mark.asyncio
async def test_multi_role_group_admin_is_allowed() -> None:
    tenant_id = uuid4()
    group_id = uuid4()

    repository = AsyncMock(spec=ConversationSearchRepository)

    repository.search.return_value = []

    service = ConversationSearchService(repository)

    await service.search(
        context=AuthorizationContext(
            actor_id="multi-role-user",
            tenant_id=tenant_id,
            roles=frozenset(
                {
                    Role.EMPLOYEE,
                    Role.GROUP_ADMIN,
                }
            ),
        ),
        actor=ConversationActorContext(
            employee_id=uuid4(),
            administered_group_ids=(frozenset({group_id})),
        ),
        filters=ConversationSearchFilters(),
        limit=50,
        offset=0,
    )

    repository.search.assert_awaited_once()
