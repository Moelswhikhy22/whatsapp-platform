from __future__ import annotations

import hashlib
import re
from uuid import UUID


_SEGMENT_PATTERN = re.compile(r"[^a-z0-9_-]+")


def _normalized_segment(
    value: str,
) -> str:
    normalized = _SEGMENT_PATTERN.sub(
        "_",
        value.strip().lower(),
    ).strip("_")

    if not normalized:
        raise ValueError("Redis key segment cannot be empty.")

    return normalized


def _identity_digest(
    value: str,
) -> str:
    normalized = value.strip()

    if not normalized:
        raise ValueError("Redis key identity cannot be empty.")

    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32]


class RedisKeys:
    @staticmethod
    def tenant_prefix(
        tenant_id: UUID,
    ) -> str:
        return f"tenant:{tenant_id}"

    @classmethod
    def rate_limit(
        cls,
        *,
        tenant_id: UUID,
        bucket: str,
        identity: str,
    ) -> str:
        return (
            f"{cls.tenant_prefix(tenant_id)}:"
            "rate_limit:"
            f"{_normalized_segment(bucket)}:"
            f"{_identity_digest(identity)}"
        )

    @classmethod
    def short_lock(
        cls,
        *,
        tenant_id: UUID,
        resource_type: str,
        resource_id: str,
    ) -> str:
        return (
            f"{cls.tenant_prefix(tenant_id)}:"
            "lock:"
            f"{_normalized_segment(resource_type)}:"
            f"{_identity_digest(resource_id)}"
        )

    @classmethod
    def cache_prefix(
        cls,
        *,
        tenant_id: UUID,
        namespace: str,
    ) -> str:
        return f"{cls.tenant_prefix(tenant_id)}:cache:{_normalized_segment(namespace)}"

    @classmethod
    def cache(
        cls,
        *,
        tenant_id: UUID,
        namespace: str,
        identity: str,
    ) -> str:
        return (
            f"{cls.cache_prefix(tenant_id=tenant_id, namespace=namespace)}:"
            f"{_identity_digest(identity)}"
        )

    @staticmethod
    def global_rate_limit(
        *,
        bucket: str,
        identity: str,
    ) -> str:
        return f"global:rate_limit:{_normalized_segment(bucket)}:{_identity_digest(identity)}"
