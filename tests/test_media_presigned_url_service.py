from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import (
    AsyncMock,
    MagicMock,
)
from uuid import uuid4

import pytest

from app.authorization.context import (
    AuthorizationContext,
)
from app.authorization.conversation import (
    ConversationActorContext,
)
from app.authorization.roles import Role
from app.db.models.conversation import (
    ConversationState,
)
from app.integrations.s3.client import (
    ManagedS3Client,
)
from app.repositories.media_access import (
    MediaAccessRepository,
)
from app.services.media_presigned_url import (
    MediaAccessDeniedError,
    MediaNotFoundError,
    MediaPresignedURLService,
)


@pytest.mark.asyncio
async def test_authorized_user_gets_short_lived_url() -> None:
    tenant_id = uuid4()
    message_id = uuid4()
    media_id = uuid4()
    conversation_id = uuid4()
    group_id = uuid4()
    employee_id = uuid4()

    now = datetime(
        2026,
        10,
        13,
        9,
        0,
        tzinfo=UTC,
    )

    repository = MagicMock(spec=MediaAccessRepository)

    repository.get_media = AsyncMock(
        return_value=SimpleNamespace(
            id=media_id,
            tenant_id=tenant_id,
            message_id=message_id,
            bucket="whatsapp-media",
            object_key=("prod/test/object"),
            deleted_at=None,
            retention_until=(now + timedelta(days=30)),
        )
    )

    repository.get_message = AsyncMock(
        return_value=SimpleNamespace(
            id=message_id,
            tenant_id=tenant_id,
            conversation_id=(conversation_id),
        )
    )

    repository.get_conversation = AsyncMock(
        return_value=SimpleNamespace(
            id=conversation_id,
            tenant_id=tenant_id,
            group_id=group_id,
            responsible_employee_id=(employee_id),
            state=(ConversationState.CLAIMED),
        )
    )

    repository.get_group = AsyncMock(
        return_value=SimpleNamespace(
            id=group_id,
            tenant_id=tenant_id,
            team_read_after_claim=False,
        )
    )

    storage = AsyncMock(spec=ManagedS3Client)

    storage.generate_presigned_get_url.return_value = (
        "http://localhost:9002/whatsapp-media/object?signed=yes"
    )

    service = MediaPresignedURLService(
        repository=repository,
        storage=storage,
        expiry_seconds=300,
        clock=lambda: now,
    )

    result = await service.create_url(
        message_id=message_id,
        media_id=media_id,
        context=AuthorizationContext(
            actor_id="employee-user",
            role=Role.EMPLOYEE,
            tenant_id=tenant_id,
        ),
        actor=ConversationActorContext(
            employee_id=employee_id,
            member_group_ids=(frozenset({group_id})),
        ),
    )

    assert result.expires_in_seconds == 300

    assert result.expires_at == (now + timedelta(seconds=300))

    storage.generate_presigned_get_url.assert_awaited_once_with(
        bucket="whatsapp-media",
        key="prod/test/object",
        expires_in_seconds=300,
    )


@pytest.mark.asyncio
async def test_unauthorized_employee_never_gets_presigned_url() -> None:
    tenant_id = uuid4()
    message_id = uuid4()
    media_id = uuid4()
    conversation_id = uuid4()
    group_id = uuid4()

    owner_id = uuid4()
    other_employee_id = uuid4()

    now = datetime.now(UTC)

    repository = MagicMock(spec=MediaAccessRepository)

    repository.get_media = AsyncMock(
        return_value=SimpleNamespace(
            tenant_id=tenant_id,
            bucket="whatsapp-media",
            object_key="object",
            deleted_at=None,
            retention_until=(now + timedelta(days=1)),
        )
    )

    repository.get_message = AsyncMock(
        return_value=SimpleNamespace(
            tenant_id=tenant_id,
            conversation_id=(conversation_id),
        )
    )

    repository.get_conversation = AsyncMock(
        return_value=SimpleNamespace(
            tenant_id=tenant_id,
            group_id=group_id,
            responsible_employee_id=(owner_id),
            state=(ConversationState.CLAIMED),
        )
    )

    repository.get_group = AsyncMock(
        return_value=SimpleNamespace(
            team_read_after_claim=False,
        )
    )

    storage = AsyncMock(spec=ManagedS3Client)

    service = MediaPresignedURLService(
        repository=repository,
        storage=storage,
        expiry_seconds=300,
        clock=lambda: now,
    )

    with pytest.raises(MediaAccessDeniedError):
        await service.create_url(
            message_id=message_id,
            media_id=media_id,
            context=(
                AuthorizationContext(
                    actor_id=("other-employee"),
                    role=Role.EMPLOYEE,
                    tenant_id=tenant_id,
                )
            ),
            actor=(
                ConversationActorContext(
                    employee_id=(other_employee_id),
                    member_group_ids=(frozenset({group_id})),
                )
            ),
        )

    storage.generate_presigned_get_url.assert_not_awaited()


@pytest.mark.asyncio
async def test_expired_media_cannot_receive_url() -> None:
    tenant_id = uuid4()
    message_id = uuid4()
    media_id = uuid4()

    now = datetime.now(UTC)

    repository = MagicMock(spec=MediaAccessRepository)

    repository.get_media = AsyncMock(
        return_value=SimpleNamespace(
            tenant_id=tenant_id,
            deleted_at=None,
            retention_until=(now - timedelta(seconds=1)),
        )
    )

    storage = AsyncMock(spec=ManagedS3Client)

    service = MediaPresignedURLService(
        repository=repository,
        storage=storage,
        expiry_seconds=120,
        clock=lambda: now,
    )

    with pytest.raises(MediaNotFoundError):
        await service.create_url(
            message_id=message_id,
            media_id=media_id,
            context=AuthorizationContext(
                actor_id="admin",
                role=Role.TENANT_ADMIN,
                tenant_id=tenant_id,
            ),
            actor=(ConversationActorContext()),
        )

    storage.generate_presigned_get_url.assert_not_awaited()
