from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
)


class Settings(BaseSettings):
    """Process-level configuration.

    Tenant integration secrets do not belong in this object. They are stored in
    Vault and resolved by authorized backend services.

    Platform infrastructure credentials may still be supplied through the
    process environment during local development. Production secret delivery
    will be hardened in the Vault section.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: Literal[
        "local",
        "test",
        "staging",
        "production",
    ] = "local"

    app_name: str = "whatsapp-multitenant-platform"

    log_level: str = "INFO"

    database_url: str = Field(
        default=("postgresql+asyncpg://app:change-me@localhost:5432/whatsapp_platform")
    )

    redis_url: str = "redis://localhost:6379/0"

    rabbitmq_url: str = "amqp://app:change-me@localhost:5672/"

    keycloak_base_url: str = "http://localhost:8080"

    keycloak_realm: str = "whatsapp-platform"

    keycloak_client_id: str = "whatsapp-platform-bff"

    # Managed S3-compatible storage.
    s3_endpoint_url: str | None = "http://localhost:9000"

    s3_region: str = "us-east-1"

    s3_bucket: str = "whatsapp-platform-dev"

    s3_access_key_id: str | None = None

    s3_secret_access_key: str | None = None

    s3_session_token: str | None = None

    s3_addressing_style: Literal[
        "auto",
        "virtual",
        "path",
    ] = "path"

    s3_public_endpoint_url: str | None = None

    media_presigned_url_expiry_seconds: int = Field(
        default=300,
        gt=0,
        le=3600,
    )
    media_retention_days: int = Field(
        default=365,
        gt=0,
    )

    vault_addr: str = "http://localhost:8200"

    vault_token: str | None = None
    vault_token_file: str | None = None
    vault_namespace: str | None = None

    vault_verify: bool = True

    vault_timeout_seconds: int = Field(
        default=10,
        gt=0,
    )

    vault_kv_mount_point: str = "secret"
    vault_path_root: str = "whatsapp-platform"
    vault_secret_cache_ttl_seconds: int = Field(
        default=60,
        gt=0,
        le=300,
    )
    meta_http_timeout_seconds: float = Field(
        default=15.0,
        gt=0,
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached process settings."""

    return Settings()
