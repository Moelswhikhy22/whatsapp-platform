from app.audit_payload import (
    REDACTED_AUDIT_VALUE,
    sanitize_audit_payload,
    sanitize_request_path,
)


def test_sanitizes_sensitive_keys_recursively() -> None:
    payload = {
        "provider": "meta",
        "access_token": "very-secret-token",
        "nested": {
            "client_secret": "secret-client-value",
            "safe": "keep-me",
        },
        "items": [
            {
                "api_key": "secret-api-key",
                "name": "safe-name",
            }
        ],
    }

    result = sanitize_audit_payload(payload)

    assert result is not None

    assert result["access_token"] == REDACTED_AUDIT_VALUE

    nested = result["nested"]

    assert isinstance(nested, dict)

    assert nested["client_secret"] == REDACTED_AUDIT_VALUE

    assert nested["safe"] == "keep-me"

    items = result["items"]

    assert isinstance(items, list)

    first = items[0]

    assert isinstance(first, dict)

    assert first["api_key"] == REDACTED_AUDIT_VALUE

    assert first["name"] == "safe-name"


def test_preserves_vault_secret_reference() -> None:
    result = sanitize_audit_payload(
        {"vault_secret_reference": ("secret/whatsapp-platform/tenants/abc/meta/main")}
    )

    assert result == {"vault_secret_reference": ("secret/whatsapp-platform/tenants/abc/meta/main")}


def test_sanitizes_camel_case_sensitive_keys() -> None:
    result = sanitize_audit_payload(
        {
            "clientSecret": "secret",
            "accessToken": "token",
        }
    )

    assert result == {
        "clientSecret": REDACTED_AUDIT_VALUE,
        "accessToken": REDACTED_AUDIT_VALUE,
    }


def test_request_path_drops_query_string() -> None:
    assert sanitize_request_path(("/api/v1/messages?access_token=secret")) == "/api/v1/messages"


def test_request_path_drops_full_url_host_and_query() -> None:
    assert (
        sanitize_request_path(("https://example.test/api/v1/media?X-Amz-Signature=secret"))
        == "/api/v1/media"
    )
