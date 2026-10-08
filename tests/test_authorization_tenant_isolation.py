from __future__ import annotations

from uuid import UUID

import pytest

from app.authorization.tenant_isolation import (
    TenantIsolationError,
    ensure_same_tenant,
    is_same_tenant,
)

TENANT_A_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

TENANT_B_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


def test_same_tenant_is_allowed() -> None:
    ensure_same_tenant(
        TENANT_A_ID,
        TENANT_A_ID,
    )


def test_foreign_tenant_is_rejected() -> None:
    with pytest.raises(TenantIsolationError):
        ensure_same_tenant(
            TENANT_A_ID,
            TENANT_B_ID,
        )


def test_missing_current_tenant_fails_closed() -> None:
    with pytest.raises(TenantIsolationError):
        ensure_same_tenant(
            None,
            TENANT_A_ID,
        )


def test_is_same_tenant_returns_true_for_same_tenant() -> None:
    assert is_same_tenant(
        TENANT_A_ID,
        TENANT_A_ID,
    )


def test_is_same_tenant_returns_false_for_foreign_tenant() -> None:
    assert not is_same_tenant(
        TENANT_A_ID,
        TENANT_B_ID,
    )


def test_is_same_tenant_returns_false_without_context() -> None:
    assert not is_same_tenant(
        None,
        TENANT_A_ID,
    )


def test_tenant_isolation_error_does_not_include_tenant_ids() -> None:
    with pytest.raises(TenantIsolationError) as exc_info:
        ensure_same_tenant(
            TENANT_A_ID,
            TENANT_B_ID,
        )

    message = str(exc_info.value)

    assert str(TENANT_A_ID) not in message
    assert str(TENANT_B_ID) not in message
