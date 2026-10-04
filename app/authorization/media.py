from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.authorization.context import AuthorizationContext
from app.authorization.conversation import (
    ConversationAccessResource,
    ConversationActorContext,
    ConversationVisibilityPolicy,
    can_view_conversation,
)
from app.authorization.permissions import Permission
from app.authorization.policy import require_permission
from app.authorization.tenant_isolation import ensure_same_tenant


@dataclass(frozen=True, slots=True)
class MediaAccessResource:
    """Authorization-relevant snapshot of a media object.

    Storage details such as bucket names and object keys are
    intentionally excluded because they must never grant access.
    """

    tenant_id: UUID


def can_access_media(
    context: AuthorizationContext,
    actor: ConversationActorContext,
    conversation: ConversationAccessResource,
    media: MediaAccessResource,
    visibility_policy: ConversationVisibilityPolicy,
) -> bool:
    """Return whether the actor may access media from a conversation.

    Media access requires all of the following:

    1. The media belongs to the active tenant.
    2. The actor may view the parent conversation.
    3. The actor's role grants media:read.

    This function authorizes access only. It does not generate a
    presigned URL and does not communicate with S3.
    """

    ensure_same_tenant(
        context.tenant_id,
        media.tenant_id,
    )

    if not can_view_conversation(
        context,
        actor,
        conversation,
        visibility_policy,
    ):
        return False

    require_permission(
        context,
        Permission.MEDIA_READ,
    )

    return True
