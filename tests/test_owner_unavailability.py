from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.db.models.conversation import (
    Conversation,
    ConversationState,
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
from app.services.owner_unavailability import (
    OwnerUnavailabilityAction,
    OwnerUnavailabilityConflictError,
    OwnerUnavailabilityService,
)


NOW = datetime(
    2026,
    10,
    12,
    12,
    0,
    tzinfo=UTC,
)


def _conversation(
    *,
    tenant_id,
    group_id,
    owner_id,
) -> Conversation:
    return Conversation(
        id=uuid4(),
        tenant_id=tenant_id,
        whatsapp_number_id=uuid4(),
        customer_contact_id=uuid4(),
        group_id=group_id,
        state=ConversationState.OPEN,
        responsible_employee_id=owner_id,
    )


def _group(
    *,
    tenant_id,
    group_id,
    policy,
    grace=300,
) -> Group:
    return Group(
        id=group_id,
        tenant_id=tenant_id,
        name="Sales",
        owner_unavailable_policy=policy,
        offline_grace_seconds=grace,
    )


def _service(
    *,
    conversation,
    group,
):
    conversation_repository = AsyncMock(
        spec=ConversationRepository,
    )
    group_repository = AsyncMock(
        spec=GroupRepository,
    )
    history_repository = MagicMock(
        spec=ConversationAssignmentHistoryRepository,
    )
    audit_repository = MagicMock(
        spec=BusinessAuditLogRepository,
    )
    outbox_repository = MagicMock(
        spec=OutboxEventRepository,
    )
    presence_store = AsyncMock(
        spec=PresenceStore,
    )

    conversation_repository.get_by_id.return_value = conversation
    group_repository.get_by_id.return_value = group

    service = OwnerUnavailabilityService(
        conversation_repository=(conversation_repository),
        group_repository=group_repository,
        assignment_history_repository=(history_repository),
        audit_repository=audit_repository,
        outbox_repository=outbox_repository,
        presence_store=presence_store,
        clock=lambda: NOW,
    )

    return (
        service,
        conversation_repository,
        group_repository,
        history_repository,
        audit_repository,
        outbox_repository,
        presence_store,
    )


@pytest.mark.asyncio
async def test_online_owner_is_not_reassigned() -> None:
    tenant_id = uuid4()
    group_id = uuid4()
    owner_id = uuid4()

    conversation = _conversation(
        tenant_id=tenant_id,
        group_id=group_id,
        owner_id=owner_id,
    )

    group = _group(
        tenant_id=tenant_id,
        group_id=group_id,
        policy=OwnerUnavailablePolicy.AUTO_REASSIGN,
    )

    (
        service,
        repository,
        _,
        history,
        _,
        outbox,
        presence,
    ) = _service(
        conversation=conversation,
        group=group,
    )

    presence.get_status.return_value = PresenceStatus.ONLINE

    result = await service.handle_new_customer_work(
        conversation_id=conversation.id,
    )

    assert result.action is OwnerUnavailabilityAction.NO_ACTION

    repository.atomic_reassign_owner.assert_not_awaited()
    history.add_auto_reassignment.assert_not_called()
    outbox.add_event.assert_not_called()


@pytest.mark.asyncio
async def test_busy_owner_is_not_treated_as_unavailable() -> None:
    tenant_id = uuid4()
    group_id = uuid4()
    owner_id = uuid4()

    conversation = _conversation(
        tenant_id=tenant_id,
        group_id=group_id,
        owner_id=owner_id,
    )

    group = _group(
        tenant_id=tenant_id,
        group_id=group_id,
        policy=OwnerUnavailablePolicy.RETURN_TO_QUEUE,
    )

    service, repository, _, _, _, _, presence = _service(
        conversation=conversation,
        group=group,
    )

    presence.get_status.return_value = PresenceStatus.BUSY

    result = await service.handle_new_customer_work(
        conversation_id=conversation.id,
    )

    assert result.action is OwnerUnavailabilityAction.NO_ACTION

    repository.atomic_return_to_queue.assert_not_awaited()


@pytest.mark.asyncio
async def test_offline_owner_inside_grace_is_kept() -> None:
    tenant_id = uuid4()
    group_id = uuid4()
    owner_id = uuid4()

    conversation = _conversation(
        tenant_id=tenant_id,
        group_id=group_id,
        owner_id=owner_id,
    )

    group = _group(
        tenant_id=tenant_id,
        group_id=group_id,
        policy=OwnerUnavailablePolicy.RETURN_TO_QUEUE,
        grace=300,
    )

    service, repository, _, _, _, _, presence = _service(
        conversation=conversation,
        group=group,
    )

    presence.get_status.return_value = PresenceStatus.OFFLINE
    presence.get_last_seen.return_value = NOW - timedelta(seconds=100)

    result = await service.handle_new_customer_work(
        conversation_id=conversation.id,
    )

    assert result.action is OwnerUnavailabilityAction.NO_ACTION

    repository.atomic_return_to_queue.assert_not_awaited()


@pytest.mark.asyncio
async def test_keep_owner_policy_keeps_expired_offline_owner() -> None:
    tenant_id = uuid4()
    group_id = uuid4()
    owner_id = uuid4()

    conversation = _conversation(
        tenant_id=tenant_id,
        group_id=group_id,
        owner_id=owner_id,
    )

    group = _group(
        tenant_id=tenant_id,
        group_id=group_id,
        policy=OwnerUnavailablePolicy.KEEP_OWNER,
    )

    service, _, _, _, _, _, presence = _service(
        conversation=conversation,
        group=group,
    )

    presence.get_status.return_value = PresenceStatus.OFFLINE
    presence.get_last_seen.return_value = NOW - timedelta(seconds=301)

    result = await service.handle_new_customer_work(
        conversation_id=conversation.id,
    )

    assert result.action is OwnerUnavailabilityAction.KEEP_OWNER


@pytest.mark.asyncio
async def test_return_to_queue_preserves_history_and_event() -> None:
    tenant_id = uuid4()
    group_id = uuid4()
    owner_id = uuid4()

    conversation = _conversation(
        tenant_id=tenant_id,
        group_id=group_id,
        owner_id=owner_id,
    )

    group = _group(
        tenant_id=tenant_id,
        group_id=group_id,
        policy=OwnerUnavailablePolicy.RETURN_TO_QUEUE,
    )

    (
        service,
        repository,
        _,
        history,
        audit,
        outbox,
        presence,
    ) = _service(
        conversation=conversation,
        group=group,
    )

    presence.get_status.return_value = PresenceStatus.UNAVAILABLE

    queued = _conversation(
        tenant_id=tenant_id,
        group_id=group_id,
        owner_id=owner_id,
    )
    queued.id = conversation.id
    queued.state = ConversationState.QUEUED
    queued.responsible_employee_id = None

    repository.atomic_return_to_queue.return_value = queued
    repository.list_eligible_team_member_ids.return_value = [
        uuid4(),
        uuid4(),
    ]

    result = await service.handle_new_customer_work(
        conversation_id=conversation.id,
    )

    assert result.action is OwnerUnavailabilityAction.RETURN_TO_QUEUE

    repository.atomic_return_to_queue.assert_awaited_once_with(
        conversation_id=conversation.id,
        expected_owner_id=owner_id,
        expected_current_state=ConversationState.OPEN,
    )

    history.add_return_to_queue.assert_called_once_with(
        conversation_id=conversation.id,
        previous_employee_id=owner_id,
    )

    audit.add_system_conversation_assignment_change.assert_called_once()
    outbox.add_event.assert_called_once()


@pytest.mark.asyncio
async def test_auto_reassign_selects_online_member() -> None:
    tenant_id = uuid4()
    group_id = uuid4()
    owner_id = uuid4()
    offline_candidate = uuid4()
    online_candidate = uuid4()

    conversation = _conversation(
        tenant_id=tenant_id,
        group_id=group_id,
        owner_id=owner_id,
    )

    group = _group(
        tenant_id=tenant_id,
        group_id=group_id,
        policy=OwnerUnavailablePolicy.AUTO_REASSIGN,
    )

    (
        service,
        repository,
        _,
        history,
        audit,
        outbox,
        presence,
    ) = _service(
        conversation=conversation,
        group=group,
    )

    presence.get_status.side_effect = [
        PresenceStatus.UNAVAILABLE,
        PresenceStatus.OFFLINE,
        PresenceStatus.ONLINE,
    ]

    repository.list_eligible_team_member_ids.return_value = [
        owner_id,
        offline_candidate,
        online_candidate,
    ]

    reassigned = _conversation(
        tenant_id=tenant_id,
        group_id=group_id,
        owner_id=online_candidate,
    )
    reassigned.id = conversation.id

    repository.atomic_reassign_owner.return_value = reassigned

    result = await service.handle_new_customer_work(
        conversation_id=conversation.id,
    )

    assert result.action is OwnerUnavailabilityAction.AUTO_REASSIGNED
    assert result.new_owner_id == online_candidate

    repository.atomic_reassign_owner.assert_awaited_once_with(
        conversation_id=conversation.id,
        expected_owner_id=owner_id,
        expected_current_state=ConversationState.OPEN,
        new_owner_id=online_candidate,
    )

    history.add_auto_reassignment.assert_called_once_with(
        conversation_id=conversation.id,
        previous_employee_id=owner_id,
        new_employee_id=online_candidate,
    )

    audit.add_system_conversation_assignment_change.assert_called_once()
    outbox.add_event.assert_called_once()


@pytest.mark.asyncio
async def test_auto_reassign_without_candidate_notifies_admin() -> None:
    tenant_id = uuid4()
    group_id = uuid4()
    owner_id = uuid4()
    candidate_id = uuid4()
    admin_id = uuid4()

    conversation = _conversation(
        tenant_id=tenant_id,
        group_id=group_id,
        owner_id=owner_id,
    )

    group = _group(
        tenant_id=tenant_id,
        group_id=group_id,
        policy=OwnerUnavailablePolicy.AUTO_REASSIGN,
    )

    (
        service,
        repository,
        group_repository,
        _,
        _,
        outbox,
        presence,
    ) = _service(
        conversation=conversation,
        group=group,
    )

    presence.get_status.side_effect = [
        PresenceStatus.UNAVAILABLE,
        PresenceStatus.OFFLINE,
    ]

    repository.list_eligible_team_member_ids.return_value = [
        owner_id,
        candidate_id,
    ]

    group_repository.list_active_admin_employee_ids.return_value = [
        admin_id,
    ]

    result = await service.handle_new_customer_work(
        conversation_id=conversation.id,
    )

    assert result.action is OwnerUnavailabilityAction.NOTIFIED_ADMIN

    repository.atomic_reassign_owner.assert_not_awaited()

    outbox.add_event.assert_called_once()

    assert outbox.add_event.call_args.kwargs["event_type"] == "conversation.owner_unavailable"


@pytest.mark.asyncio
async def test_notify_admin_policy_creates_durable_event() -> None:
    tenant_id = uuid4()
    group_id = uuid4()
    owner_id = uuid4()
    admin_id = uuid4()

    conversation = _conversation(
        tenant_id=tenant_id,
        group_id=group_id,
        owner_id=owner_id,
    )

    group = _group(
        tenant_id=tenant_id,
        group_id=group_id,
        policy=OwnerUnavailablePolicy.NOTIFY_ADMIN,
    )

    (
        service,
        _,
        group_repository,
        _,
        _,
        outbox,
        presence,
    ) = _service(
        conversation=conversation,
        group=group,
    )

    presence.get_status.return_value = PresenceStatus.UNAVAILABLE

    group_repository.list_active_admin_employee_ids.return_value = [
        admin_id,
    ]

    result = await service.handle_new_customer_work(
        conversation_id=conversation.id,
    )

    assert result.action is OwnerUnavailabilityAction.NOTIFIED_ADMIN

    outbox.add_event.assert_called_once()


@pytest.mark.asyncio
async def test_concurrent_owner_change_raises_conflict() -> None:
    tenant_id = uuid4()
    group_id = uuid4()
    owner_id = uuid4()

    conversation = _conversation(
        tenant_id=tenant_id,
        group_id=group_id,
        owner_id=owner_id,
    )

    group = _group(
        tenant_id=tenant_id,
        group_id=group_id,
        policy=OwnerUnavailablePolicy.RETURN_TO_QUEUE,
    )

    (
        service,
        repository,
        _,
        history,
        _,
        _,
        presence,
    ) = _service(
        conversation=conversation,
        group=group,
    )

    presence.get_status.return_value = PresenceStatus.UNAVAILABLE

    repository.atomic_return_to_queue.return_value = None

    with pytest.raises(
        OwnerUnavailabilityConflictError,
    ):
        await service.handle_new_customer_work(
            conversation_id=conversation.id,
        )

    history.add_return_to_queue.assert_not_called()
