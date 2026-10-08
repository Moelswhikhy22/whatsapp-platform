from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.authorization.context import (
    AuthorizationContext,
)
from app.authorization.conversation import (
    ConversationAccessResource,
    ConversationActorContext,
    ConversationVisibilityPolicy,
)
from app.authorization.errors import (
    AuthorizationDeniedError,
)
from app.authorization.media import (
    MediaAccessResource,
    can_access_media,
)
from app.db.models.conversation import (
    ConversationState,
)
from app.integrations.s3.client import (
    ManagedS3Client,
)
from app.repositories.media_access import (
    MediaAccessRepository,
)


class MediaPresignedURLError(RuntimeError):
    pass


class MediaNotFoundError(MediaPresignedURLError):
    pass


class MediaAccessDeniedError(MediaPresignedURLError):
    pass


class MediaStorageUnavailableError(MediaPresignedURLError):
    pass


@dataclass(
    frozen=True,
    slots=True,
)
class MediaPresignedURLResult:
    url: str
    expires_in_seconds: int
    expires_at: datetime


class MediaPresignedURLService:
    def __init__(
        self,
        *,
        repository: MediaAccessRepository,
        storage: ManagedS3Client,
        expiry_seconds: int,
        clock: Callable[
            [],
            datetime,
        ]
        | None = None,
    ) -> None:
        if expiry_seconds <= 0:
            raise ValueError(("Presigned URL expiry must be greater than zero."))

        self._repository = repository
        self._storage = storage
        self._expiry_seconds = expiry_seconds

        self._clock = clock if clock is not None else lambda: datetime.now(UTC)

    async def create_url(
        self,
        *,
        message_id: UUID,
        media_id: UUID,
        context: AuthorizationContext,
        actor: ConversationActorContext,
    ) -> MediaPresignedURLResult:
        media = await self._repository.get_media(
            message_id=message_id,
            media_id=media_id,
        )

        if media is None:
            raise MediaNotFoundError

        now = self._clock()

        if media.deleted_at is not None:
            raise MediaNotFoundError

        if media.retention_until <= now:
            raise MediaNotFoundError

        message = await self._repository.get_message(message_id)

        if message is None:
            raise MediaNotFoundError

        conversation = await self._repository.get_conversation(message.conversation_id)

        if conversation is None:
            raise MediaNotFoundError

        group_id = conversation.group_id

        if group_id is None:
            raise MediaNotFoundError

        group = await self._repository.get_group(group_id)

        if group is None:
            raise MediaNotFoundError

        conversation_resource = ConversationAccessResource(
            tenant_id=(conversation.tenant_id),
            group_id=group_id,
            responsible_employee_id=(conversation.responsible_employee_id),
            is_queued=(conversation.state is ConversationState.QUEUED),
        )

        visibility_policy = ConversationVisibilityPolicy(
            team_read_after_claim=(group.team_read_after_claim)
        )

        try:
            allowed = can_access_media(
                context,
                actor,
                conversation_resource,
                MediaAccessResource(tenant_id=(media.tenant_id)),
                visibility_policy,
            )

        except AuthorizationDeniedError as exc:
            raise (MediaAccessDeniedError) from exc

        if not allowed:
            raise MediaAccessDeniedError

        try:
            url = await self._storage.generate_presigned_get_url(
                bucket=media.bucket,
                key=media.object_key,
                expires_in_seconds=(self._expiry_seconds),
            )

        except Exception as exc:
            raise (MediaStorageUnavailableError(("Could not create temporary media URL."))) from exc

        return MediaPresignedURLResult(
            url=url,
            expires_in_seconds=(self._expiry_seconds),
            expires_at=(now + timedelta(seconds=(self._expiry_seconds))),
        )
