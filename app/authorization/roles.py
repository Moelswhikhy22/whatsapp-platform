from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    PLATFORM_ADMIN = "platform_admin"
    TENANT_ADMIN = "tenant_admin"
    GROUP_ADMIN = "group_admin"
    EMPLOYEE = "employee"
    INTEGRATION = "integration"
