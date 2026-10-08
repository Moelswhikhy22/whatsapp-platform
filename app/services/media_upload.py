from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from io import BytesIO
from uuid import UUID, uuid4

from app.db.models.media_object import MediaObject
from app.integrations.s3.client import ManagedS3Client
from app.repositories.media import MediaRepository
from app.services.media_object_key import MediaObjectKeyBuilder


class MediaUploadError(RuntimeError):
    pass


class MediaMessageNotFoundError(MediaUploadError):
    pass


class MediaUploadInvalidError(MediaUploadError):
    pass


class MediaStorageUnavailableError(MediaUploadError):
    pass


class MediaMetadataPersistenceError(MediaUploadError):
    pass


class MediaUploadService:
    def __init__(
        self,
        *,
        repository: MediaRepository,
        storage: ManagedS3Client,
        bucket: str,
        key_builder: MediaObjectKeyBuilder,
        retention_days: int,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not bucket.strip():
            raise ValueError("S3 bucket must not be blank.")

        if retention_days <= 0:
            raise ValueError("Media retention days must be greater than zero.")

        self._repository = repository
        self._storage = storage
        self._bucket = bucket.strip()
        self._key_builder = key_builder
        self._retention_days = retention_days

        self._clock = clock if clock is not None else lambda: datetime.now(UTC)

    async def upload_bytes(
        self,
        *,
        message_id: UUID,
        data: bytes,
        mime_type: str,
        original_filename: str | None = None,
        media_id: UUID | None = None,
        cleanup_on_persistence_failure: bool = True,
    ) -> MediaObject:
        normalized_mime_type = mime_type.strip()

        if not normalized_mime_type:
            raise MediaUploadInvalidError("MIME type must not be blank.")

        if len(normalized_mime_type) > 255:
            raise MediaUploadInvalidError("MIME type exceeds 255 characters.")

        if original_filename is not None and len(original_filename) > 512:
            raise MediaUploadInvalidError("Original filename exceeds 512 characters.")

        message = await self._repository.get_message(message_id)

        if message is None:
            raise MediaMessageNotFoundError

        resolved_media_id = media_id if media_id is not None else uuid4()

        object_key = self._key_builder.build(
            tenant_id=self._repository.tenant_id,
            conversation_id=message.conversation_id,
            message_id=message.id,
            media_id=resolved_media_id,
        )

        sha256 = hashlib.sha256(data).hexdigest()

        try:
            await self._storage.upload_fileobj(
                fileobj=BytesIO(data),
                bucket=self._bucket,
                key=object_key,
                content_type=normalized_mime_type,
                metadata={
                    "tenant-id": str(self._repository.tenant_id),
                    "message-id": str(message.id),
                    "media-id": str(resolved_media_id),
                    "sha256": sha256,
                },
            )

        except Exception as exc:
            raise MediaStorageUnavailableError("Failed to upload media to object storage.") from exc

        retention_until = self._clock() + timedelta(days=self._retention_days)

        media = self._repository.add_media_object(
            media_id=resolved_media_id,
            message_id=message.id,
            bucket=self._bucket,
            object_key=object_key,
            original_filename=original_filename,
            mime_type=normalized_mime_type,
            size_bytes=len(data),
            sha256=sha256,
            retention_until=retention_until,
        )

        try:
            await self._repository.flush()

        except Exception as exc:
            if cleanup_on_persistence_failure:
                try:
                    await self._storage.delete_object(
                        bucket=self._bucket,
                        key=object_key,
                    )

                except Exception as cleanup_exc:
                    raise MediaMetadataPersistenceError(
                        "Media metadata persistence failed and uploaded object cleanup also failed."
                    ) from cleanup_exc

            raise MediaMetadataPersistenceError("Media metadata persistence failed.") from exc

        return media
