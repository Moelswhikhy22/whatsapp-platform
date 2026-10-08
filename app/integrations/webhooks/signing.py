from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any


def serialize_webhook_payload(
    payload: dict[str, Any],
) -> bytes:
    return json.dumps(
        payload,
        separators=(",", ":"),
        sort_keys=True,
        default=str,
    ).encode("utf-8")


def sign_webhook_payload(
    *,
    signing_secret: str,
    timestamp: str,
    body: bytes,
) -> str:
    signed_payload = timestamp.encode("utf-8") + b"." + body

    digest = hmac.new(
        signing_secret.encode("utf-8"),
        signed_payload,
        hashlib.sha256,
    ).hexdigest()

    return f"v1={digest}"
