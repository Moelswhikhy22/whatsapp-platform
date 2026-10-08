from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from app.authorization.permissions import Permission
from app.authorization.roles import Role


ROLE_PERMISSIONS: Mapping[
    Role,
    frozenset[Permission],
] = MappingProxyType(
    {
        Role.PLATFORM_ADMIN: frozenset(
            {
                Permission.PLATFORM_TENANT_CREATE,
                Permission.PLATFORM_TENANT_READ,
                Permission.PLATFORM_TENANT_UPDATE,
                Permission.PLATFORM_TENANT_SUSPEND,
                Permission.AUDIT_READ,
            }
        ),
        Role.TENANT_ADMIN: frozenset(
            {
                Permission.TENANT_READ,
                Permission.TENANT_UPDATE,
                Permission.CONVERSATION_READ,
                Permission.CONVERSATION_CLAIM,
                Permission.CONVERSATION_CLOSE,
                Permission.CONVERSATION_REOPEN,
                Permission.CONVERSATION_REASSIGN,
                Permission.CONVERSATION_TRANSFER,
                Permission.CONVERSATION_ESCALATE,
                Permission.MESSAGE_SEND,
                Permission.CUSTOMER_READ,
                Permission.CUSTOMER_UPDATE,
                Permission.GROUP_READ,
                Permission.GROUP_MANAGE,
                Permission.GROUP_MANAGE_MEMBERS,
                Permission.EMPLOYEE_READ,
                Permission.EMPLOYEE_MANAGE,
                Permission.TEMPLATE_READ,
                Permission.TEMPLATE_CREATE,
                Permission.TEMPLATE_UPDATE,
                Permission.TEMPLATE_SUBMIT,
                Permission.TEMPLATE_SEND,
                Permission.MEDIA_READ,
                Permission.INTEGRATION_READ,
                Permission.INTEGRATION_MANAGE,
                Permission.INTEGRATION_CREDENTIALS_UPDATE,
                Permission.WEBHOOK_MANAGE,
                Permission.AUDIT_READ,
            }
        ),
        Role.GROUP_ADMIN: frozenset(
            {
                Permission.CONVERSATION_READ,
                Permission.CONVERSATION_CLAIM,
                Permission.CONVERSATION_CLOSE,
                Permission.CONVERSATION_REOPEN,
                Permission.CONVERSATION_REASSIGN,
                Permission.CONVERSATION_TRANSFER,
                Permission.CONVERSATION_ESCALATE,
                Permission.MESSAGE_SEND,
                Permission.CUSTOMER_READ,
                Permission.CUSTOMER_UPDATE,
                Permission.GROUP_READ,
                Permission.GROUP_MANAGE_MEMBERS,
                Permission.EMPLOYEE_READ,
                Permission.TEMPLATE_READ,
                Permission.TEMPLATE_CREATE,
                Permission.TEMPLATE_UPDATE,
                Permission.TEMPLATE_SEND,
                Permission.MEDIA_READ,
            }
        ),
        Role.EMPLOYEE: frozenset(
            {
                Permission.CONVERSATION_READ,
                Permission.CONVERSATION_CLAIM,
                Permission.CONVERSATION_CLOSE,
                Permission.CONVERSATION_ESCALATE,
                Permission.MESSAGE_SEND,
                Permission.CUSTOMER_READ,
                Permission.GROUP_READ,
                Permission.TEMPLATE_READ,
                Permission.TEMPLATE_SEND,
                Permission.MEDIA_READ,
            }
        ),
        Role.INTEGRATION: frozenset(
            {
                Permission.CONVERSATION_READ,
                Permission.MESSAGE_SEND,
                Permission.CUSTOMER_READ,
                Permission.WEBHOOK_MANAGE,
            }
        ),
    }
)


def permissions_for_role(
    role: Role,
) -> frozenset[Permission]:
    return ROLE_PERMISSIONS[role]


def role_has_permission(
    role: Role,
    permission: Permission,
) -> bool:
    return permission in permissions_for_role(role)
