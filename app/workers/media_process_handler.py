from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import cast
from uuid import UUID

from aio_pika.abc import (
    AbstractIncomingMessage,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
)

from app.integrations.rabbitmq.consumer import (
    PermanentMessageError,
)
from app.services.meta_media import (
    MetaMediaPermanentProcessingError,
    MetaMediaProcessingService,
)


@dataclass(
    frozen=True,
    slots=True,
)
class MediaProcessJob:
    tenant_id: UUID
    message_id: UUID
    provider_media_id: str
    original_filename: str | None
    webhook_mime_type: str | None


MediaProcessorFactory = Callable[
    [
        AsyncSession,
        UUID,
    ],
    MetaMediaProcessingService,
]


class InvalidMediaProcessJobError(PermanentMessageError):
    pass


class MediaProcessRabbitMQHandler:
    def __init__(
        self,
        *,
        session_factory: (async_sessionmaker[AsyncSession]),
        service_factory: (MediaProcessorFactory),
    ) -> None:
        self._session_factory = session_factory
        self._service_factory = service_factory

    async def __call__(
        self,
        message: AbstractIncomingMessage,
    ) -> None:
        job = self._parse_job(message.body)

        try:
            await self._dispatch(job)

        except MetaMediaPermanentProcessingError as exc:
            raise PermanentMessageError(str(exc)) from exc

    async def _dispatch(
        self,
        job: MediaProcessJob,
    ) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                service = self._service_factory(
                    session,
                    job.tenant_id,
                )

                await service.process(
                    message_id=(job.message_id),
                    provider_media_id=(job.provider_media_id),
                    original_filename=(job.original_filename),
                    webhook_mime_type=(job.webhook_mime_type),
                )

    @staticmethod
    def _parse_job(
        body: bytes,
    ) -> MediaProcessJob:
        try:
            decoded = json.loads(body)

        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
        ) as exc:
            raise (InvalidMediaProcessJobError(("Media process job is not valid JSON."))) from exc

        if not isinstance(
            decoded,
            dict,
        ):
            raise (InvalidMediaProcessJobError(("Media process job must be an object.")))

        envelope = cast(
            dict[str, object],
            decoded,
        )

        if envelope.get("event_type") != "media.process":
            raise (InvalidMediaProcessJobError(("Unexpected media event type.")))

        if envelope.get("aggregate_type") != "message":
            raise (InvalidMediaProcessJobError(("Media job aggregate must be a message.")))

        tenant_id = MediaProcessRabbitMQHandler._required_uuid(
            envelope,
            "tenant_id",
        )

        raw_payload = envelope.get("payload")

        if not isinstance(
            raw_payload,
            dict,
        ):
            raise (InvalidMediaProcessJobError(("Media process payload is missing.")))

        payload = cast(
            dict[str, object],
            raw_payload,
        )

        message_id = MediaProcessRabbitMQHandler._required_uuid(
            payload,
            "message_id",
        )

        aggregate_id = envelope.get("aggregate_id")

        if not isinstance(
            aggregate_id,
            str,
        ) or aggregate_id != str(message_id):
            raise (
                InvalidMediaProcessJobError(("Media job aggregate ID does not match message_id."))
            )

        provider_media_id = payload.get("provider_media_id")

        if not isinstance(
            provider_media_id,
            str,
        ) or not (provider_media_id.strip()):
            raise (InvalidMediaProcessJobError(("provider_media_id is missing.")))

        original_filename = MediaProcessRabbitMQHandler._optional_string(
            payload,
            "original_filename",
        )

        webhook_mime_type = MediaProcessRabbitMQHandler._optional_string(
            payload,
            "webhook_mime_type",
        )

        return MediaProcessJob(
            tenant_id=tenant_id,
            message_id=message_id,
            provider_media_id=(provider_media_id.strip()),
            original_filename=(original_filename),
            webhook_mime_type=(webhook_mime_type),
        )

    @staticmethod
    def _required_uuid(
        value: dict[str, object],
        key: str,
    ) -> UUID:
        raw_value = value.get(key)

        if not isinstance(
            raw_value,
            str,
        ):
            raise (InvalidMediaProcessJobError(f"{key} is missing."))

        try:
            return UUID(raw_value)

        except ValueError as exc:
            raise (InvalidMediaProcessJobError(f"{key} is invalid.")) from exc

    @staticmethod
    def _optional_string(
        value: dict[str, object],
        key: str,
    ) -> str | None:
        raw_value = value.get(key)

        if raw_value is None:
            return None

        if not isinstance(
            raw_value,
            str,
        ):
            raise (InvalidMediaProcessJobError(f"{key} is invalid."))

        normalized = raw_value.strip()

        return normalized or None
