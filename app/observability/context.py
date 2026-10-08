from __future__ import annotations

from contextvars import (
    ContextVar,
    Token,
)
from dataclasses import dataclass
from uuid import UUID


_trace_id_var: ContextVar[str | None] = ContextVar(
    "observability_trace_id",
    default=None,
)

_tenant_id_var: ContextVar[str | None] = ContextVar(
    "observability_tenant_id",
    default=None,
)


@dataclass(
    frozen=True,
    slots=True,
)
class LogContext:
    trace_id: str | None
    tenant_id: str | None


@dataclass(
    frozen=True,
    slots=True,
)
class LogContextTokens:
    trace_id: Token[str | None]
    tenant_id: Token[str | None]


def bind_log_context(
    *,
    trace_id: str | None = None,
    tenant_id: UUID | str | None = None,
) -> LogContextTokens:
    normalized_trace_id = _normalize_optional_string(trace_id)

    normalized_tenant_id = _normalize_tenant_id(tenant_id)

    return LogContextTokens(
        trace_id=_trace_id_var.set(normalized_trace_id),
        tenant_id=_tenant_id_var.set(normalized_tenant_id),
    )


def reset_log_context(
    tokens: LogContextTokens,
) -> None:
    _trace_id_var.reset(tokens.trace_id)

    _tenant_id_var.reset(tokens.tenant_id)


def get_log_context() -> LogContext:
    return LogContext(
        trace_id=_trace_id_var.get(),
        tenant_id=_tenant_id_var.get(),
    )


def _normalize_tenant_id(
    value: UUID | str | None,
) -> str | None:
    if value is None:
        return None

    if isinstance(
        value,
        UUID,
    ):
        return str(value)

    return _normalize_optional_string(value)


def _normalize_optional_string(
    value: str | None,
) -> str | None:
    if value is None:
        return None

    normalized = value.strip()

    return normalized or None
