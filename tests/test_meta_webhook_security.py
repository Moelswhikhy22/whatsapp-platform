from __future__ import annotations

import hashlib
import hmac

from app.integrations.meta.webhook_security import (
    derive_provider_event_key,
    verify_meta_challenge_token,
    verify_meta_signature,
)


def test_valid_meta_signature_is_accepted() -> None:
    body = b'{"object":"whatsapp_business_account"}'
    secret = "app-secret"

    digest = hmac.new(
        secret.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()

    assert verify_meta_signature(
        raw_body=body,
        signature_header=f"sha256={digest}",
        app_secret=secret,
    )


def test_invalid_meta_signature_is_rejected() -> None:
    assert not verify_meta_signature(
        raw_body=b"payload",
        signature_header=("sha256=" + ("0" * 64)),
        app_secret="app-secret",
    )


def test_missing_signature_is_rejected() -> None:
    assert not verify_meta_signature(
        raw_body=b"payload",
        signature_header=None,
        app_secret="app-secret",
    )


def test_challenge_token_matches() -> None:
    assert verify_meta_challenge_token(
        received_token="verify-me",
        expected_token="verify-me",
    )


def test_event_key_is_stable() -> None:
    body = b'{"hello":"world"}'

    first = derive_provider_event_key(body)
    second = derive_provider_event_key(body)

    assert first == second
    assert first.startswith("body-sha256:")


def test_different_payload_has_different_key() -> None:
    assert derive_provider_event_key(b'{"value":1}') != derive_provider_event_key(b'{"value":2}')
