from __future__ import annotations

from app.audit_payload import (
    REDACTED_AUDIT_VALUE,
    sanitize_audit_payload,
    sanitize_request_path,
)


def test_redacts_prefixed_and_camel_case_secrets() -> None:
    payload = {
        "meta_access_token": "meta-secret",
        "stripe_api_key": "stripe-secret",
        "oauthRefreshToken": "refresh-secret",
        "clientSecret": "client-secret",
        "aws_private_key": "private-secret",
        "databasePasswordHash": "password-value",
    }

    result = sanitize_audit_payload(payload)

    assert result == {
        "meta_access_token": (REDACTED_AUDIT_VALUE),
        "stripe_api_key": (REDACTED_AUDIT_VALUE),
        "oauthRefreshToken": (REDACTED_AUDIT_VALUE),
        "clientSecret": (REDACTED_AUDIT_VALUE),
        "aws_private_key": (REDACTED_AUDIT_VALUE),
        "databasePasswordHash": (REDACTED_AUDIT_VALUE),
    }


def test_nested_secret_variants_are_redacted() -> None:
    payload = {
        "config": {
            "provider": "meta",
            "nested": [
                {"whatsappAccessToken": ("secret-1")},
                {"authorization_header": ("Bearer secret-2")},
            ],
        },
    }

    result = sanitize_audit_payload(payload)

    assert result is not None

    config = result["config"]

    assert isinstance(
        config,
        dict,
    )

    assert "secret-1" not in str(result)

    assert "secret-2" not in str(result)

    assert str(REDACTED_AUDIT_VALUE) in str(result)


def test_safe_secret_references_are_preserved() -> None:
    payload = {
        "vault_secret_reference": ("whatsapp-platform/tenants/tenant-a/meta/main"),
        "signing_secret_configured": True,
        "credentials_configured": True,
        "token_type": "Bearer",
    }

    result = sanitize_audit_payload(payload)

    assert result == payload


def test_presigned_url_is_redacted() -> None:
    result = sanitize_audit_payload(
        {"media_presigned_url": ("https://storage.example/object?signature=secret")}
    )

    assert result == {"media_presigned_url": (REDACTED_AUDIT_VALUE)}


def test_request_path_removes_query_and_fragment() -> None:
    result = sanitize_request_path(
        ("https://tenant.example/api/v1/messages?access_token=secret#section")
    )

    assert result == ("/api/v1/messages")
