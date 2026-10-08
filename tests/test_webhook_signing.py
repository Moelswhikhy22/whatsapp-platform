from app.integrations.webhooks.signing import (
    serialize_webhook_payload,
    sign_webhook_payload,
)


def test_webhook_signature_is_stable() -> None:
    body = serialize_webhook_payload(
        {
            "type": "message.received",
            "data": {
                "message_id": "123",
            },
        }
    )

    first = sign_webhook_payload(
        signing_secret=("a" * 32),
        timestamp="1791880000",
        body=body,
    )

    second = sign_webhook_payload(
        signing_secret=("a" * 32),
        timestamp="1791880000",
        body=body,
    )

    assert first == second
    assert first.startswith("v1=")


def test_signature_changes_when_payload_changes() -> None:
    secret = "a" * 32

    first = sign_webhook_payload(
        signing_secret=secret,
        timestamp="1791880000",
        body=serialize_webhook_payload({"value": 1}),
    )

    second = sign_webhook_payload(
        signing_secret=secret,
        timestamp="1791880000",
        body=serialize_webhook_payload({"value": 2}),
    )

    assert first != second
