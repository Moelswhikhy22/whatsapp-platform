from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from uuid import UUID, uuid4

from app.db.models.conversation import (
    Conversation,
)
from app.db.models.group import (
    Group,
    OwnerUnavailablePolicy,
)
from app.presence import (
    PresenceStatus,
    PresenceStore,
)
from app.repositories.business_audit_log import (
    BusinessAuditLogRepository,
)
from app.repositories.conversation import (
    ConversationRepository,
)
from app.repositories.conversation_assignment_history import (
    ConversationAssignmentHistoryRepository,
)
from app.repositories.group import GroupRepository
from app.repositories.outbox_event import (
    OutboxEventRepository,
)


class OwnerUnavailabilityError(RuntimeError):
    pass


class OwnerUnavailabilityNotFoundError(OwnerUnavailabilityError):
    pass


class OwnerUnavailabilityConflictError(OwnerUnavailabilityError):
    pass


class OwnerUnavailabilityAction(StrEnum):
    NO_ACTION = "no_action"
    KEEP_OWNER = "keep_owner"
    RETURN_TO_QUEUE = "return_to_queue"
    AUTO_REASSIGNED = "auto_reassigned"
    NOTIFIED_ADMIN = "notified_admin"


@dataclass(frozen=True, slots=True)
class OwnerUnavailabilityResult:
    action: OwnerUnavailabilityAction
    previous_owner_id: UUID | None
    new_owner_id: UUID | None = None


class OwnerUnavailabilityService:
    def __init__(
        self,
        *,
        conversation_repository: ConversationRepository,
        group_repository: GroupRepository,
        assignment_history_repository: (ConversationAssignmentHistoryRepository),
        audit_repository: BusinessAuditLogRepository,
        outbox_repository: OutboxEventRepository,
        presence_store: PresenceStore,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._conversation_repository = conversation_repository
        self._group_repository = group_repository
        self._assignment_history_repository = assignment_history_repository
        self._audit_repository = audit_repository
        self._outbox_repository = outbox_repository
        self._presence_store = presence_store
        self._clock = clock or (lambda: datetime.now(UTC))

    async def handle_new_customer_work(
        self,
        *,
        conversation_id: UUID,
    ) -> OwnerUnavailabilityResult:
        conversation = await self._conversation_repository.get_by_id(
            conversation_id,
        )

        if conversation is None:
            raise OwnerUnavailabilityNotFoundError

        owner_id = conversation.responsible_employee_id
        group_id = conversation.group_id

        if owner_id is None or group_id is None:
            return OwnerUnavailabilityResult(
                action=(OwnerUnavailabilityAction.NO_ACTION),
                previous_owner_id=owner_id,
            )

        group = await self._group_repository.get_by_id(
            group_id,
        )

        if group is None:
            raise OwnerUnavailabilityNotFoundError

        if not await self._policy_is_due(
            group=group,
            owner_id=owner_id,
        ):
            return OwnerUnavailabilityResult(
                action=(OwnerUnavailabilityAction.NO_ACTION),
                previous_owner_id=owner_id,
            )

        policy = group.owner_unavailable_policy

        if policy is OwnerUnavailablePolicy.KEEP_OWNER:
            return OwnerUnavailabilityResult(
                action=(OwnerUnavailabilityAction.KEEP_OWNER),
                previous_owner_id=owner_id,
            )

        if policy is OwnerUnavailablePolicy.RETURN_TO_QUEUE:
            return await self._return_to_queue(
                conversation=conversation,
                owner_id=owner_id,
            )

        if policy is OwnerUnavailablePolicy.AUTO_REASSIGN:
            return await self._auto_reassign(
                conversation=conversation,
                group=group,
                owner_id=owner_id,
            )

        if policy is OwnerUnavailablePolicy.NOTIFY_ADMIN:
            await self._notify_admin(
                conversation=conversation,
                reason="owner_unavailable",
            )

            return OwnerUnavailabilityResult(
                action=(OwnerUnavailabilityAction.NOTIFIED_ADMIN),
                previous_owner_id=owner_id,
            )

        raise OwnerUnavailabilityError(f"Unsupported owner policy: {policy}")

    async def _policy_is_due(
        self,
        *,
        group: Group,
        owner_id: UUID,
    ) -> bool:
        status = await self._presence_store.get_status(
            tenant_id=group.tenant_id,
            employee_id=owner_id,
        )

        if status in {
            PresenceStatus.ONLINE,
            PresenceStatus.BUSY,
        }:
            return False

        if status is PresenceStatus.UNAVAILABLE:
            return True

        last_seen = await self._presence_store.get_last_seen(
            tenant_id=group.tenant_id,
            employee_id=owner_id,
        )

        if last_seen is None:
            return False

        now = self._clock()

        if last_seen > now:
            return False

        offline_for = now - last_seen

        return offline_for >= timedelta(
            seconds=group.offline_grace_seconds,
        )

    async def _return_to_queue(
        self,
        *,
        conversation: Conversation,
        owner_id: UUID,
    ) -> OwnerUnavailabilityResult:
        group_id = conversation.group_id

        if group_id is None:
            raise OwnerUnavailabilityNotFoundError

        updated = await self._conversation_repository.atomic_return_to_queue(
            conversation_id=conversation.id,
            expected_owner_id=owner_id,
            expected_current_state=(conversation.state),
        )

        if updated is None:
            raise OwnerUnavailabilityConflictError

        self._assignment_history_repository.add_return_to_queue(
            conversation_id=conversation.id,
            previous_employee_id=owner_id,
        )

        trace_id = uuid4().hex

        self._audit_repository.add_system_conversation_assignment_change(
            conversation_id=conversation.id,
            action=("conversation.returned_to_queue"),
            before_json={
                "state": conversation.state.value,
                "responsible_employee_id": str(owner_id),
            },
            after_json={
                "state": "queued",
                "responsible_employee_id": None,
            },
            trace_id=trace_id,
        )

        recipient_ids = await self._conversation_repository.list_eligible_team_member_ids(
            group_id,
        )

        self._outbox_repository.add_event(
            event_type="conversation.queued",
            aggregate_type="conversation",
            aggregate_id=str(conversation.id),
            payload_json={
                "conversation_id": str(
                    conversation.id,
                ),
                "group_id": str(group_id),
                "recipient_employee_ids": [str(employee_id) for employee_id in recipient_ids],
                "reason": "owner_unavailable",
            },
        )

        return OwnerUnavailabilityResult(
            action=(OwnerUnavailabilityAction.RETURN_TO_QUEUE),
            previous_owner_id=owner_id,
        )

    async def _auto_reassign(
        self,
        *,
        conversation: Conversation,
        group: Group,
        owner_id: UUID,
    ) -> OwnerUnavailabilityResult:
        candidate_id = await self._find_available_candidate(
            group=group,
            current_owner_id=owner_id,
        )

        if candidate_id is None:
            await self._notify_admin(
                conversation=conversation,
                reason=("no_available_reassignment_candidate"),
            )

            return OwnerUnavailabilityResult(
                action=(OwnerUnavailabilityAction.NOTIFIED_ADMIN),
                previous_owner_id=owner_id,
            )

        updated = await self._conversation_repository.atomic_reassign_owner(
            conversation_id=conversation.id,
            expected_owner_id=owner_id,
            expected_current_state=(conversation.state),
            new_owner_id=candidate_id,
        )

        if updated is None:
            raise OwnerUnavailabilityConflictError

        self._assignment_history_repository.add_auto_reassignment(
            conversation_id=conversation.id,
            previous_employee_id=owner_id,
            new_employee_id=candidate_id,
        )

        trace_id = uuid4().hex

        self._audit_repository.add_system_conversation_assignment_change(
            conversation_id=conversation.id,
            action="conversation.reassigned",
            before_json={
                "state": conversation.state.value,
                "responsible_employee_id": str(owner_id),
            },
            after_json={
                "state": updated.state.value,
                "responsible_employee_id": str(candidate_id),
            },
            trace_id=trace_id,
        )

        self._outbox_repository.add_event(
            event_type="conversation.reassigned",
            aggregate_type="conversation",
            aggregate_id=str(conversation.id),
            payload_json={
                "conversation_id": str(
                    conversation.id,
                ),
                "group_id": str(group.id),
                "previous_employee_id": str(
                    owner_id,
                ),
                "new_employee_id": str(
                    candidate_id,
                ),
                "reason": "owner_unavailable",
            },
        )

        return OwnerUnavailabilityResult(
            action=(OwnerUnavailabilityAction.AUTO_REASSIGNED),
            previous_owner_id=owner_id,
            new_owner_id=candidate_id,
        )

    async def _find_available_candidate(
        self,
        *,
        group: Group,
        current_owner_id: UUID,
    ) -> UUID | None:
        employee_ids = await self._conversation_repository.list_eligible_team_member_ids(
            group.id,
        )

        for employee_id in employee_ids:
            if employee_id == current_owner_id:
                continue

            status = await self._presence_store.get_status(
                tenant_id=group.tenant_id,
                employee_id=employee_id,
            )

            if status is PresenceStatus.ONLINE:
                return employee_id

        return None

    async def _notify_admin(
        self,
        *,
        conversation: Conversation,
        reason: str,
    ) -> None:
        group_id = conversation.group_id

        if group_id is None:
            return

        admin_ids = await self._group_repository.list_active_admin_employee_ids(
            group_id,
        )

        self._outbox_repository.add_event(
            event_type=("conversation.owner_unavailable"),
            aggregate_type="conversation",
            aggregate_id=str(conversation.id),
            payload_json={
                "conversation_id": str(
                    conversation.id,
                ),
                "group_id": str(group_id),
                "responsible_employee_id": (
                    str(conversation.responsible_employee_id)
                    if (conversation.responsible_employee_id is not None)
                    else None
                ),
                "recipient_employee_ids": [str(employee_id) for employee_id in admin_ids],
                "reason": reason,
            },
        )
