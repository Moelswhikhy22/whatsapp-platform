from __future__ import annotations
from uuid import UUID
import hashlib
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import (
    AsyncMock,
    MagicMock,
)
from uuid import uuid4

import pytest

from app.db.models.media_object import (
    MediaObject,
)
from app.integrations.s3.client import (
    ManagedS3Client,
)
from app.repositories.media import (
    MediaRepository,
)
from app.services.media_object_key import (
    MediaObjectKeyBuilder,
)
from app.services.media_upload import (
    MediaMessageNotFoundError,
    MediaStorageUnavailableError,
    MediaUploadService,
)


@pytest.mark.asyncio
async def test_upload_persists_media_metadata() -> None:
    tenant_id = uuid4()
    conversation_id = uuid4()
    message_id = uuid4()

    repository = MagicMock(spec=MediaRepository)
    repository.tenant_id = tenant_id

    repository.get_message = AsyncMock(
        return_value=SimpleNamespace(
            id=message_id,
            conversation_id=(conversation_id),
        )
    )

    repository.flush = AsyncMock()

    def add_media_object(
        **kwargs: object,
    ) -> MediaObject:
        media_id = kwargs.pop("media_id")
        assert isinstance(
            media_id,
            UUID,
        )

        return MediaObject(
            id=media_id,
            tenant_id=tenant_id,
            **kwargs,
        )

    repository.add_media_object.side_effect = add_media_object

    storage = AsyncMock(spec=ManagedS3Client)

    now = datetime(
        2026,
        10,
        13,
        9,
        0,
        tzinfo=UTC,
    )

    service = MediaUploadService(
        repository=repository,
        storage=storage,
        bucket="whatsapp-media",
        key_builder=(MediaObjectKeyBuilder(environment="production")),
        retention_days=365,
        clock=lambda: now,
    )

    data = b"hello-media"

    media = await service.upload_bytes(
        message_id=message_id,
        data=data,
        mime_type="image/jpeg",
        original_filename="photo.jpg",
    )

    assert media.tenant_id == tenant_id
    assert media.message_id == message_id
    assert media.bucket == ("whatsapp-media")

    assert media.object_key.startswith(
        (f"prod/{tenant_id}/whatsapp/{conversation_id}/{message_id}/")
    )

    assert media.size_bytes == len(data)

    assert media.sha256 == (hashlib.sha256(data).hexdigest())

    assert media.mime_type == ("image/jpeg")

    assert media.original_filename == ("photo.jpg")

    assert media.retention_until > now

    storage.upload_fileobj.assert_awaited_once()
    repository.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_foreign_or_missing_message_is_rejected_before_s3() -> None:
    repository = MagicMock(spec=MediaRepository)
    repository.tenant_id = uuid4()

    repository.get_message = AsyncMock(return_value=None)

    storage = AsyncMock(spec=ManagedS3Client)

    service = MediaUploadService(
        repository=repository,
        storage=storage,
        bucket="whatsapp-media",
        key_builder=(MediaObjectKeyBuilder(environment="test")),
        retention_days=365,
    )

    with pytest.raises(MediaMessageNotFoundError):
        await service.upload_bytes(
            message_id=uuid4(),
            data=b"abc",
            mime_type="image/png",
        )

    storage.upload_fileobj.assert_not_awaited()


@pytest.mark.asyncio
async def test_s3_failure_does_not_persist_metadata() -> None:
    tenant_id = uuid4()
    message_id = uuid4()

    repository = MagicMock(spec=MediaRepository)
    repository.tenant_id = tenant_id

    repository.get_message = AsyncMock(
        return_value=SimpleNamespace(
            id=message_id,
            conversation_id=uuid4(),
        )
    )

    storage = AsyncMock(spec=ManagedS3Client)

    storage.upload_fileobj.side_effect = RuntimeError("S3 unavailable")

    service = MediaUploadService(
        repository=repository,
        storage=storage,
        bucket="whatsapp-media",
        key_builder=(MediaObjectKeyBuilder(environment="test")),
        retention_days=365,
    )

    with pytest.raises(MediaStorageUnavailableError):
        await service.upload_bytes(
            message_id=message_id,
            data=b"abc",
            mime_type="image/png",
        )

    repository.add_media_object.assert_not_called()
