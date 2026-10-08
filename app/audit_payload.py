from __future__ import annotations

import re
from urllib.parse import urlsplit


REDACTED_AUDIT_VALUE = "[REDACTED]"


_SAFE_NORMALIZED_KEYS = frozenset(
    {
        "credentialsconfigured",
        "signingsecretconfigured",
        "clientsecretconfigured",
        "appsecretconfigured",
        "webhooksecretconfigured",
        "secretreference",
        "vaultsecretreference",
        "vaultsecretpath",
        "tokentype",
    }
)


_SENSITIVE_EXACT_KEYS = frozenset(
    {
        "authorization",
        "authorizationheader",
        "cookie",
        "cookies",
        "setcookie",
        "password",
        "passphrase",
        "token",
        "secret",
        "apikey",
        "privatekey",
        "presignedurl",
        "sessionid",
    }
)


_SENSITIVE_SUFFIXES = (
    "accesstoken",
    "refreshtoken",
    "idtoken",
    "clientsecret",
    "appsecret",
    "webhooksecret",
    "signingsecret",
    "vaulttoken",
    "apikey",
    "privatekey",
    "secretaccesskey",
    "accesskeyid",
    "presignedurl",
    "sessionid",
    "sessioncookie",
)


def sanitize_audit_payload(
    payload: dict[str, object] | None,
) -> dict[str, object] | None:
    if payload is None:
        return None

    sanitized = _sanitize_value(payload)

    if not isinstance(
        sanitized,
        dict,
    ):
        raise TypeError("Audit payload must remain a dictionary.")

    return sanitized


def sanitize_request_path(
    request_path: str | None,
) -> str | None:
    if request_path is None:
        return None

    normalized = request_path.strip()

    if not normalized:
        return None

    parsed = urlsplit(normalized)

    path = parsed.path

    if not path:
        return "/"

    return path


def _sanitize_value(
    value: object,
) -> object:
    if isinstance(
        value,
        dict,
    ):
        return {
            str(key): (
                REDACTED_AUDIT_VALUE if _is_sensitive_key(str(key)) else _sanitize_value(item)
            )
            for key, item in value.items()
        }

    if isinstance(
        value,
        list,
    ):
        return [_sanitize_value(item) for item in value]

    if isinstance(
        value,
        tuple,
    ):
        return [_sanitize_value(item) for item in value]

    return value


def _is_sensitive_key(
    key: str,
) -> bool:
    normalized = _normalize_key(key)

    if normalized in _SAFE_NORMALIZED_KEYS:
        return False

    if normalized in _SENSITIVE_EXACT_KEYS:
        return True

    if any(normalized.endswith(suffix) for suffix in _SENSITIVE_SUFFIXES):
        return True

    if "password" in normalized:
        return True

    if "authorization" in normalized:
        return True

    if "cookie" in normalized:
        return True

    if "presignedurl" in normalized:
        return True

    return False


def _normalize_key(
    key: str,
) -> str:
    return re.sub(
        r"[^a-z0-9]",
        "",
        key.lower(),
    )
