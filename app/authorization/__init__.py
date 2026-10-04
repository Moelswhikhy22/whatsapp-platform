from app.authorization.context import AuthorizationContext
from app.authorization.conversation import (
    ConversationAccessResource,
    ConversationActorContext,
    ConversationReassignmentTarget,
    ConversationSendPolicy,
    ConversationTransferDestination,
    ConversationVisibilityPolicy,
    can_claim_conversation,
    can_reassign_conversation,
    can_send_message,
    can_transfer_conversation,
    can_view_conversation,
)
from app.authorization.customer import (
    CustomerAccessResource,
    CustomerActorContext,
    can_modify_customer,
)
from app.authorization.errors import AuthorizationDeniedError
from app.authorization.integration import (
    IntegrationAccessResource,
    IntegrationAction,
    can_manage_integrations,
)
from app.authorization.media import (
    MediaAccessResource,
    can_access_media,
)
from app.authorization.permissions import Permission
from app.authorization.policy import (
    has_permission,
    require_permission,
    require_tenant_permission,
)
from app.authorization.role_permissions import (
    ROLE_PERMISSIONS,
    permissions_for_role,
    role_has_permission,
)
from app.authorization.roles import Role
from app.authorization.template import (
    TemplateAccessResource,
    TemplateAction,
    TemplateType,
    can_manage_templates,
)
from app.authorization.tenant_isolation import (
    TenantIsolationError,
    ensure_same_tenant,
    is_same_tenant,
)

__all__ = [
    "ROLE_PERMISSIONS",
    "AuthorizationContext",
    "AuthorizationDeniedError",
    "ConversationAccessResource",
    "ConversationActorContext",
    "ConversationReassignmentTarget",
    "ConversationSendPolicy",
    "ConversationTransferDestination",
    "ConversationVisibilityPolicy",
    "CustomerAccessResource",
    "CustomerActorContext",
    "IntegrationAccessResource",
    "IntegrationAction",
    "MediaAccessResource",
    "Permission",
    "Role",
    "TemplateAccessResource",
    "TemplateAction",
    "TemplateType",
    "TenantIsolationError",
    "can_access_media",
    "can_claim_conversation",
    "can_manage_integrations",
    "can_manage_templates",
    "can_modify_customer",
    "can_reassign_conversation",
    "can_send_message",
    "can_transfer_conversation",
    "can_view_conversation",
    "ensure_same_tenant",
    "has_permission",
    "is_same_tenant",
    "permissions_for_role",
    "require_permission",
    "require_tenant_permission",
    "role_has_permission",
]
