from __future__ import annotations

from app.authorization.conversation import (
    ConversationSendPolicy,
    ConversationVisibilityPolicy,
)
from app.db.models.group import Group


def conversation_visibility_policy_from_group(
    group: Group,
) -> ConversationVisibilityPolicy:
    return ConversationVisibilityPolicy(
        team_read_after_claim=group.team_read_after_claim,
    )


def conversation_send_policy_from_group(
    group: Group,
) -> ConversationSendPolicy:
    return ConversationSendPolicy(
        allow_non_owner_employee_send=(group.allow_non_owner_employee_send),
    )
