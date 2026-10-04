from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from uuid import UUID

from app.authorization.context import AuthorizationContext
from app.authorization.permissions import Permission
from app.authorization.policy import require_tenant_permission


class IntegrationAction(StrEnum):
    READ = "read"
    CREATE = "create"
    UPDATE = "update"
    VALIDATE = "validate"
    CREDENTIALS_UPDATE = "credentials_update"


@dataclass(frozen=True, slots=True)
class IntegrationAccessResource:
    """Authorization-relevant snapshot of an integration.

    Integration configuration is tenant-scoped.

    Secret values, Vault paths, access tokens, passwords, and API keys
    are intentionally excluded from the authorization resource.
    Authorization decisions must never depend on secret contents.
    """

    tenant_id: UUID


_INTEGRATION_ACTION_PERMISSIONS: Mapping[
    IntegrationAction,
    Permission,
] = MappingProxyType(
    {
        IntegrationAction.READ: Permission.INTEGRATION_READ,
        IntegrationAction.CREATE: Permission.INTEGRATION_MANAGE,
        IntegrationAction.UPDATE: Permission.INTEGRATION_MANAGE,
        IntegrationAction.VALIDATE: Permission.INTEGRATION_MANAGE,
        IntegrationAction.CREDENTIALS_UPDATE: Permission.INTEGRATION_CREDENTIALS_UPDATE,
    }
)


def can_manage_integrations(
    context: AuthorizationContext,
    integration: IntegrationAccessResource,
    action: IntegrationAction,
) -> bool:
    """Return whether the actor may perform an integration action.

    Authorization order:

    1. Tenant isolation.
    2. Resolve the business permission required by the action.
    3. Enforce RBAC.

    Secret access and Vault operations are deliberately outside this
    policy. A successful credentials authorization only permits the
    service layer to begin the credential-update workflow.
    """

    required_permission = _INTEGRATION_ACTION_PERMISSIONS[action]

    require_tenant_permission(
        context,
        integration.tenant_id,
        required_permission,
    )

    return True
