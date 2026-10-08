from __future__ import annotations

from app.core.config import Settings
from app.integrations.s3.client import (
    ManagedS3Client,
    S3ClientConfig,
)


def create_managed_s3_client(
    settings: Settings,
) -> ManagedS3Client:
    return ManagedS3Client(
        S3ClientConfig(
            region_name=settings.s3_region,
            endpoint_url=(settings.s3_endpoint_url),
            access_key_id=(settings.s3_access_key_id),
            secret_access_key=(settings.s3_secret_access_key),
            session_token=(settings.s3_session_token),
            addressing_style=(settings.s3_addressing_style),
        )
    )
