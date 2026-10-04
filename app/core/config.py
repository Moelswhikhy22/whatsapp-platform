from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Process-level configuration.

    Tenant integration secrets do not belong in this object. They are stored in Vault and
    resolved by authorized backend services in later tasks.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: Literal["local", "test", "staging", "production"] = "local"
    app_name: str = "whatsapp-multitenant-platform"
    log_level: str = "INFO"

    database_url: str = Field(
        default="postgresql+asyncpg://app:change-me@localhost:5432/whatsapp_platform"
    )
    redis_url: str = "redis://localhost:6379/0"
    rabbitmq_url: str = "amqp://app:change-me@localhost:5672/"

    keycloak_base_url: str = "http://localhost:8080"
    keycloak_realm: str = "whatsapp-platform"
    keycloak_client_id: str = "whatsapp-platform-bff"

    s3_endpoint_url: str = "http://localhost:9000"
    s3_region: str = "us-east-1"
    s3_bucket: str = "whatsapp-platform-dev"

    vault_addr: str = "http://localhost:8200"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return immutable-by-convention process settings cached for this process."""

    return Settings()
