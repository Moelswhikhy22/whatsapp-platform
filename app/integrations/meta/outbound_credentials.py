from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.db.models.integration import Integration


@dataclass(frozen=True, slots=True)
class MetaOutboundCredentials:
    access_token: str


class MetaOutboundCredentialsUnavailableError(RuntimeError):
    """
    Raised when credentials cannot currently
    be retrieved.

    Examples:
    - Vault unavailable
    - transient authentication failure

    This condition is retryable.
    """


class MetaOutboundCredentialsInvalidError(RuntimeError):
    """
    Raised when the integration credential
    configuration is permanently invalid.

    Examples:
    - missing Vault reference
    - missing access_token in the secret
    """


class MetaOutboundCredentialProvider(Protocol):
    async def get_credentials(
        self,
        integration: Integration,
    ) -> MetaOutboundCredentials: ...
