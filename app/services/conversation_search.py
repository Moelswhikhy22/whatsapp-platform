from __future__ import annotations

from app.authorization.context import (
    AuthorizationContext,
)
from app.authorization.conversation import (
    ConversationActorContext,
)
from app.authorization.errors import (
    AuthorizationDeniedError,
)
from app.authorization.permissions import (
    Permission,
)
from app.authorization.policy import (
    require_permission,
)
from app.authorization.roles import Role
from app.repositories.conversation_search import (
    ConversationSearchFilters,
    ConversationSearchItem,
    ConversationSearchRepository,
)


class ConversationSearchService:
    def __init__(
        self,
        repository: (ConversationSearchRepository),
    ) -> None:
        self._repository = repository

    async def search(
        self,
        *,
        context: AuthorizationContext,
        actor: ConversationActorContext,
        filters: ConversationSearchFilters,
        limit: int,
        offset: int,
    ) -> list[ConversationSearchItem]:
        require_permission(
            context,
            Permission.CONVERSATION_READ,
        )

        if context.has_role(Role.TENANT_ADMIN):
            allowed_group_ids = None

        elif context.has_role(Role.GROUP_ADMIN):
            allowed_group_ids = actor.administered_group_ids

        else:
            raise AuthorizationDeniedError(Permission.CONVERSATION_READ)

        return await self._repository.search(
            filters=filters,
            allowed_group_ids=(allowed_group_ids),
            limit=limit,
            offset=offset,
        )
