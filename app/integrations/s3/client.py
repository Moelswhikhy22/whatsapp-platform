from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, BinaryIO, Literal

import aioboto3
from aiobotocore.config import AioConfig

if TYPE_CHECKING:
    from types_aiobotocore_s3.client import S3Client

AddressingStyle = Literal["auto", "virtual", "path"]


@dataclass(frozen=True, slots=True)
class S3ClientConfig:
    region_name: str | None = None
    endpoint_url: str | None = None

    access_key_id: str | None = None
    secret_access_key: str | None = None
    session_token: str | None = None

    addressing_style: AddressingStyle = "auto"


class ManagedS3Client:
    def __init__(self, config: S3ClientConfig) -> None:
        self._config = config

        self._session = aioboto3.Session(
            aws_access_key_id=config.access_key_id,
            aws_secret_access_key=config.secret_access_key,
            aws_session_token=config.session_token,
            region_name=config.region_name,
        )

        self._client_config = AioConfig(
            s3={
                "addressing_style": config.addressing_style,
            },
        )

    def _client(self) -> AbstractAsyncContextManager[S3Client]:
        return self._session.client(
            "s3",
            endpoint_url=self._config.endpoint_url,
            config=self._client_config,
        )

    async def upload_fileobj(
        self,
        *,
        fileobj: BinaryIO,
        bucket: str,
        key: str,
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> None:
        extra_args: dict[str, Any] = {}

        if content_type is not None:
            extra_args["ContentType"] = content_type

        if metadata:
            extra_args["Metadata"] = metadata

        async with self._client() as s3:
            if extra_args:
                await s3.upload_fileobj(
                    fileobj,
                    bucket,
                    key,
                    ExtraArgs=extra_args,
                )
            else:
                await s3.upload_fileobj(
                    fileobj,
                    bucket,
                    key,
                )

    async def download_fileobj(
        self,
        *,
        bucket: str,
        key: str,
        fileobj: BinaryIO,
    ) -> None:
        async with self._client() as s3:
            await s3.download_fileobj(
                bucket,
                key,
                fileobj,
            )

    async def head_object(
        self,
        *,
        bucket: str,
        key: str,
    ) -> dict[str, Any]:
        async with self._client() as s3:
            response = await s3.head_object(
                Bucket=bucket,
                Key=key,
            )

        return dict(response)

    async def delete_object(
        self,
        *,
        bucket: str,
        key: str,
    ) -> None:
        async with self._client() as s3:
            await s3.delete_object(
                Bucket=bucket,
                Key=key,
            )

    async def generate_presigned_get_url(
        self,
        *,
        bucket: str,
        key: str,
        expires_in_seconds: int,
    ) -> str:
        async with self._client() as s3:
            url = await s3.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": bucket,
                    "Key": key,
                },
                ExpiresIn=expires_in_seconds,
            )

        return str(url)
