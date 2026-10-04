from __future__ import annotations

from enum import StrEnum


class Permission(StrEnum):
    # Platform-level permissions.
    #
    # These are intentionally separate from tenant-scoped permissions.
    # Having a platform permission never grants access to tenant-owned
    # resources automatically.
    PLATFORM_TENANT_CREATE = "platform:tenant:create"
    PLATFORM_TENANT_READ = "platform:tenant:read"
    PLATFORM_TENANT_UPDATE = "platform:tenant:update"
    PLATFORM_TENANT_SUSPEND = "platform:tenant:suspend"

    # Tenant-level permissions.
    TENANT_CREATE = "tenant:create"
    TENANT_READ = "tenant:read"
    TENANT_UPDATE = "tenant:update"
    TENANT_SUSPEND = "tenant:suspend"

    CONVERSATION_READ = "conversation:read"
    CONVERSATION_CLAIM = "conversation:claim"
    CONVERSATION_CLOSE = "conversation:close"
    CONVERSATION_REOPEN = "conversation:reopen"
    CONVERSATION_REASSIGN = "conversation:reassign"
    CONVERSATION_TRANSFER = "conversation:transfer"
    CONVERSATION_ESCALATE = "conversation:escalate"

    MESSAGE_SEND = "message:send"

    CUSTOMER_READ = "customer:read"
    CUSTOMER_UPDATE = "customer:update"

    GROUP_READ = "group:read"
    GROUP_MANAGE = "group:manage"
    GROUP_MANAGE_MEMBERS = "group:manage_members"

    EMPLOYEE_READ = "employee:read"
    EMPLOYEE_MANAGE = "employee:manage"

    TEMPLATE_READ = "template:read"
    TEMPLATE_CREATE = "template:create"
    TEMPLATE_UPDATE = "template:update"
    TEMPLATE_SUBMIT = "template:submit"
    TEMPLATE_SEND = "template:send"

    MEDIA_READ = "media:read"

    INTEGRATION_READ = "integration:read"
    INTEGRATION_MANAGE = "integration:manage"
    INTEGRATION_CREDENTIALS_UPDATE = "integration:credentials_update"

    WEBHOOK_MANAGE = "webhook:manage"

    AUDIT_READ = "audit:read"
