from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from typing import Protocol

from app.db.models.integration import Integration


@dataclass(frozen=True, slots=True)
class MetaWebhookCredentials:
    verify_token: str
    app_secret: str


class MetaWebhookCredentialsUnavailableError(RuntimeError):
    """Raised when Meta webhook credentials cannot be resolved safely."""


class MetaWebhookCredentialProvider(Protocol):
    async def get_credentials(
        self,
        integration: Integration,
    ) -> MetaWebhookCredentials: ...


def verify_meta_signature(
    *,
    raw_body: bytes,
    signature_header: str | None,
    app_secret: str,
) -> bool:
    if not signature_header:
        return False

    prefix = "sha256="

    if not signature_header.startswith(prefix):
        return False

    received_digest = signature_header[len(prefix) :]

    if len(received_digest) != 64:
        return False

    expected_digest = hmac.new(
        app_secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(
        received_digest.lower(),
        expected_digest,
    )


def verify_meta_challenge_token(
    *,
    received_token: str,
    expected_token: str,
) -> bool:
    return hmac.compare_digest(
        received_token,
        expected_token,
    )


def derive_provider_event_key(
    raw_body: bytes,
) -> str:
    digest = hashlib.sha256(raw_body).hexdigest()

    return f"body-sha256:{digest}"
