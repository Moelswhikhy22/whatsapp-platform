from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Select,
    select,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from app.db.models.media_object import (
    MediaObject,
)
from app.db.models.message import Message


class MediaRepository:
    def __init__(
        self,
        *,
        session: AsyncSession,
        tenant_id: UUID,
    ) -> None:
        self._session = session
        self._tenant_id = tenant_id

    @property
    def tenant_id(self) -> UUID:
        return self._tenant_id

    async def get_message(
        self,
        message_id: UUID,
    ) -> Message | None:
        statement: Select[Message] = select(Message).where(
            Message.tenant_id == self._tenant_id,
            Message.id == message_id,
        )

        result = await self._session.scalars(statement)

        return result.first()

    async def get_by_message(
        self,
        message_id: UUID,
    ) -> MediaObject | None:
        statement: Select[MediaObject] = select(MediaObject).where(
            MediaObject.tenant_id == self._tenant_id,
            MediaObject.message_id == message_id,
        )

        result = await self._session.scalars(statement)

        return result.first()

    def add_media_object(
        self,
        *,
        media_id: UUID,
        message_id: UUID,
        bucket: str,
        object_key: str,
        original_filename: str | None,
        mime_type: str,
        size_bytes: int,
        sha256: str,
        retention_until: datetime,
    ) -> MediaObject:
        media = MediaObject(
            id=media_id,
            tenant_id=self._tenant_id,
            message_id=message_id,
            bucket=bucket,
            object_key=object_key,
            original_filename=(original_filename),
            mime_type=mime_type,
            size_bytes=size_bytes,
            sha256=sha256,
            retention_until=(retention_until),
            deleted_at=None,
        )

        self._session.add(media)

        return media

    async def flush(self) -> None:
        await self._session.flush()
