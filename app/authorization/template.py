from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from uuid import UUID

from app.authorization.context import AuthorizationContext
from app.authorization.permissions import Permission
from app.authorization.policy import require_tenant_permission


class TemplateType(StrEnum):
    INTERNAL = "internal"
    META = "meta"


class TemplateAction(StrEnum):
    READ = "read"
    CREATE = "create"
    UPDATE = "update"
    SUBMIT = "submit"
    SEND = "send"


@dataclass(frozen=True, slots=True)
class TemplateAccessResource:
    """Authorization-relevant snapshot of a template.

    Templates are tenant-wide resources in V1. Group-level template
    ownership is intentionally not modeled because it is not part of
    the current requirements or domain design.
    """

    tenant_id: UUID
    template_type: TemplateType


_TEMPLATE_ACTION_PERMISSIONS: Mapping[
    TemplateAction,
    Permission,
] = MappingProxyType(
    {
        TemplateAction.READ: Permission.TEMPLATE_READ,
        TemplateAction.CREATE: Permission.TEMPLATE_CREATE,
        TemplateAction.UPDATE: Permission.TEMPLATE_UPDATE,
        TemplateAction.SUBMIT: Permission.TEMPLATE_SUBMIT,
        TemplateAction.SEND: Permission.TEMPLATE_SEND,
    }
)


def can_manage_templates(
    context: AuthorizationContext,
    template: TemplateAccessResource,
    action: TemplateAction,
) -> bool:
    """Return whether the actor may perform an action on a template.

    Authorization order:

    1. Tenant isolation.
    2. RBAC permission corresponding to the requested action.
    3. Template-type-specific authorization rules.

    SUBMIT applies only to Meta templates. Provider lifecycle rules,
    approval state, and Meta messaging-window rules are business
    policies and are intentionally handled outside this authorization
    function.
    """

    required_permission = _TEMPLATE_ACTION_PERMISSIONS[action]

    require_tenant_permission(
        context,
        template.tenant_id,
        required_permission,
    )

    if action is TemplateAction.SUBMIT:
        return template.template_type is TemplateType.META

    return True
