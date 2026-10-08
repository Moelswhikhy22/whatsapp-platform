from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.conversation import (
    Conversation,
    ConversationState,
)
from app.db.models.customer_company import (
    CustomerCompany,
)
from app.db.models.customer_contact import (
    CustomerContact,
)
from app.db.models.integration import (
    Integration,
    IntegrationProvider,
)
from app.db.models.message import (
    ActorAttribution,
    Message,
    MessageDirection,
    MessageSource,
    MessageStatus,
    MessageType,
)
from app.db.models.tenant import (
    Tenant,
    TenantStatus,
)
from app.db.models.whatsapp_number import (
    WhatsAppNumber,
)
from app.db.rls import apply_tenant_rls_context
from app.repositories.incoming_message import (
    IncomingMessageRepository,
)
from app.tenants.context import (
    TenantContext,
    TenantContextSource,
)

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_external_message_echo_persists_source_and_unknown_actor(
    integration_session: AsyncSession,
) -> None:
    tenant_id = uuid4()
    integration_id = uuid4()
    whatsapp_number_id = uuid4()
    company_id = uuid4()
    contact_id = uuid4()
    conversation_id = uuid4()

    meta_message_id = f"wamid.integration.echo.{uuid4()}"

    meta_timestamp = datetime(
        2026,
        10,
        14,
        7,
        0,
        tzinfo=UTC,
    )

    tenant = Tenant(
        id=tenant_id,
        name="External Echo Integration Test",
        slug=f"external-echo-{tenant_id.hex}",
        status=TenantStatus.ACTIVE,
    )

    integration_session.add(tenant)

    await integration_session.flush()

    tenant_context = TenantContext.from_tenant(
        tenant,
        source=TenantContextSource.PROVIDER_IDENTITY,
    )

    await apply_tenant_rls_context(
        integration_session,
        tenant_context,
    )

    integration = Integration(
        id=integration_id,
        tenant_id=tenant_id,
        provider=IntegrationProvider.META,
        name=f"meta-external-echo-{integration_id.hex}",
        external_account_id=f"waba-{integration_id.hex}",
        keycloak_client_id=f"external-echo-{integration_id.hex}",
        config_json={},
        vault_secret_reference=None,
        active=True,
    )

    whatsapp_number = WhatsAppNumber(
        id=whatsapp_number_id,
        tenant_id=tenant_id,
        integration_id=integration_id,
        meta_phone_number_id=f"phone-{whatsapp_number_id.hex}",
        display_phone_number="+201000000000",
        active=True,
    )

    company = CustomerCompany(
        id=company_id,
        tenant_id=tenant_id,
        name="External Echo Customer",
        active=True,
    )

    contact = CustomerContact(
        id=contact_id,
        tenant_id=tenant_id,
        customer_company_id=company_id,
        display_name="External Echo Contact",
        phone_number="+201111111111",
        normalized_phone="201111111111",
        active=True,
    )

    conversation = Conversation(
        id=conversation_id,
        tenant_id=tenant_id,
        whatsapp_number_id=whatsapp_number_id,
        customer_contact_id=contact_id,
        group_id=None,
        state=ConversationState.OPEN,
        responsible_employee_id=None,
        claimed_at=None,
    )

    # Stage 1:
    # Objects that depend only on the already-persisted tenant.
    integration_session.add_all(
        [
            integration,
            company,
        ]
    )

    await integration_session.flush()

    # Stage 2:
    # Objects whose parents now exist.
    integration_session.add_all(
        [
            whatsapp_number,
            contact,
        ]
    )

    await integration_session.flush()

    # Stage 3:
    # Conversation depends on both WhatsAppNumber and CustomerContact.
    integration_session.add(conversation)

    await integration_session.flush()

    repository = IncomingMessageRepository(
        session=integration_session,
        tenant_id=tenant_id,
    )

    created_message_id = await repository.insert_external_message_if_new(
        conversation_id=conversation_id,
        meta_message_id=meta_message_id,
        message_type=MessageType.TEXT,
        body_text="Sent from WhatsApp Business App",
        meta_timestamp=meta_timestamp,
    )

    assert created_message_id is not None

    await integration_session.flush()

    integration_session.expire_all()

    statement = select(Message).where(
        Message.tenant_id == tenant_id,
        Message.id == created_message_id,
    )

    result = await integration_session.scalars(statement)

    persisted = result.one()

    assert persisted.tenant_id == tenant_id
    assert persisted.conversation_id == conversation_id

    assert persisted.meta_message_id == meta_message_id

    assert persisted.direction is (MessageDirection.OUTBOUND)

    assert persisted.source is (MessageSource.WHATSAPP_EXTERNAL)

    assert persisted.message_type is (MessageType.TEXT)

    assert persisted.body_text == ("Sent from WhatsApp Business App")

    assert persisted.status is MessageStatus.SENT

    assert persisted.actual_actor_id is None

    assert persisted.represented_employee_id is None

    assert persisted.external_actor_id is None

    assert persisted.actor_attribution is (ActorAttribution.UNKNOWN)

    assert persisted.meta_timestamp == (meta_timestamp)


@pytest.mark.asyncio
async def test_external_message_echo_meta_id_is_idempotent(
    integration_session: AsyncSession,
) -> None:
    tenant_id = uuid4()
    integration_id = uuid4()
    whatsapp_number_id = uuid4()
    company_id = uuid4()
    contact_id = uuid4()
    conversation_id = uuid4()

    meta_message_id = f"wamid.integration.echo.{uuid4()}"

    tenant = Tenant(
        id=tenant_id,
        name="External Echo Idempotency Test",
        slug=f"external-echo-idempotency-{tenant_id.hex}",
        status=TenantStatus.ACTIVE,
    )

    integration_session.add(tenant)

    await integration_session.flush()

    tenant_context = TenantContext.from_tenant(
        tenant,
        source=TenantContextSource.PROVIDER_IDENTITY,
    )

    await apply_tenant_rls_context(
        integration_session,
        tenant_context,
    )

    integration = Integration(
        id=integration_id,
        tenant_id=tenant_id,
        provider=IntegrationProvider.META,
        name=f"meta-echo-idempotency-{integration_id.hex}",
        external_account_id=f"waba-{integration_id.hex}",
        keycloak_client_id=f"echo-idempotency-{integration_id.hex}",
        config_json={},
        vault_secret_reference=None,
        active=True,
    )

    whatsapp_number = WhatsAppNumber(
        id=whatsapp_number_id,
        tenant_id=tenant_id,
        integration_id=integration_id,
        meta_phone_number_id=f"phone-{whatsapp_number_id.hex}",
        display_phone_number="+201000000001",
        active=True,
    )

    company = CustomerCompany(
        id=company_id,
        tenant_id=tenant_id,
        name="External Echo Idempotency Customer",
        active=True,
    )

    contact = CustomerContact(
        id=contact_id,
        tenant_id=tenant_id,
        customer_company_id=company_id,
        display_name="Echo Idempotency Contact",
        phone_number="+201111111112",
        normalized_phone="201111111112",
        active=True,
    )

    conversation = Conversation(
        id=conversation_id,
        tenant_id=tenant_id,
        whatsapp_number_id=whatsapp_number_id,
        customer_contact_id=contact_id,
        group_id=None,
        state=ConversationState.OPEN,
        responsible_employee_id=None,
        claimed_at=None,
    )
    # Stage 1:
    # Objects that depend only on the already-persisted tenant.
    integration_session.add_all(
        [
            integration,
            company,
        ]
    )

    await integration_session.flush()

    # Stage 2:
    # Objects whose parents now exist.
    integration_session.add_all(
        [
            whatsapp_number,
            contact,
        ]
    )

    await integration_session.flush()

    # Stage 3:
    # Conversation depends on both WhatsAppNumber and CustomerContact.
    integration_session.add(conversation)

    await integration_session.flush()

    repository = IncomingMessageRepository(
        session=integration_session,
        tenant_id=tenant_id,
    )

    first = await repository.insert_external_message_if_new(
        conversation_id=conversation_id,
        meta_message_id=meta_message_id,
        message_type=MessageType.TEXT,
        body_text="First external echo",
        meta_timestamp=None,
    )

    second = await repository.insert_external_message_if_new(
        conversation_id=conversation_id,
        meta_message_id=meta_message_id,
        message_type=MessageType.TEXT,
        body_text="Duplicate external echo",
        meta_timestamp=None,
    )

    assert first is not None
    assert second is None

    await integration_session.flush()

    statement = select(Message).where(
        Message.tenant_id == tenant_id,
        Message.meta_message_id == meta_message_id,
    )

    messages = list(await integration_session.scalars(statement))

    assert len(messages) == 1

    assert messages[0].id == first

    assert messages[0].body_text == ("First external echo")

    assert messages[0].source is (MessageSource.WHATSAPP_EXTERNAL)

    assert messages[0].actor_attribution is (ActorAttribution.UNKNOWN)


@pytest.mark.asyncio
async def test_external_message_insert_does_not_modify_conversation(
    integration_session: AsyncSession,
) -> None:
    tenant_id = uuid4()
    integration_id = uuid4()
    whatsapp_number_id = uuid4()
    company_id = uuid4()
    contact_id = uuid4()
    conversation_id = uuid4()

    tenant = Tenant(
        id=tenant_id,
        name="External Echo Conversation Test",
        slug=f"external-echo-conversation-{tenant_id.hex}",
        status=TenantStatus.ACTIVE,
    )

    integration_session.add(tenant)

    await integration_session.flush()

    tenant_context = TenantContext.from_tenant(
        tenant,
        source=TenantContextSource.PROVIDER_IDENTITY,
    )

    await apply_tenant_rls_context(
        integration_session,
        tenant_context,
    )

    integration = Integration(
        id=integration_id,
        tenant_id=tenant_id,
        provider=IntegrationProvider.META,
        name=f"meta-conversation-{integration_id.hex}",
        external_account_id=f"waba-{integration_id.hex}",
        keycloak_client_id=f"echo-conversation-{integration_id.hex}",
        config_json={},
        vault_secret_reference=None,
        active=True,
    )

    whatsapp_number = WhatsAppNumber(
        id=whatsapp_number_id,
        tenant_id=tenant_id,
        integration_id=integration_id,
        meta_phone_number_id=f"phone-{whatsapp_number_id.hex}",
        display_phone_number="+201000000002",
        active=True,
    )

    company = CustomerCompany(
        id=company_id,
        tenant_id=tenant_id,
        name="External Conversation Customer",
        active=True,
    )

    contact = CustomerContact(
        id=contact_id,
        tenant_id=tenant_id,
        customer_company_id=company_id,
        display_name="Conversation Test Contact",
        phone_number="+201111111113",
        normalized_phone="201111111113",
        active=True,
    )

    conversation = Conversation(
        id=conversation_id,
        tenant_id=tenant_id,
        whatsapp_number_id=whatsapp_number_id,
        customer_contact_id=contact_id,
        group_id=None,
        state=ConversationState.WAITING_CUSTOMER,
        responsible_employee_id=None,
        claimed_at=None,
    )

    # Stage 1:
    # Objects that depend only on the already-persisted tenant.
    integration_session.add_all(
        [
            integration,
            company,
        ]
    )

    await integration_session.flush()

    # Stage 2:
    # Objects whose parents now exist.
    integration_session.add_all(
        [
            whatsapp_number,
            contact,
        ]
    )

    await integration_session.flush()

    # Stage 3:
    # Conversation depends on both WhatsAppNumber and CustomerContact.
    integration_session.add(conversation)

    await integration_session.flush()

    original_state = conversation.state
    original_group_id = conversation.group_id
    original_owner_id = conversation.responsible_employee_id
    original_claimed_at = conversation.claimed_at

    repository = IncomingMessageRepository(
        session=integration_session,
        tenant_id=tenant_id,
    )

    message_id = await repository.insert_external_message_if_new(
        conversation_id=conversation_id,
        meta_message_id=(f"wamid.integration.echo.{uuid4()}"),
        message_type=MessageType.TEXT,
        body_text="External activity",
        meta_timestamp=None,
    )

    assert message_id is not None

    await integration_session.flush()

    integration_session.expire_all()

    refreshed_conversation = await integration_session.get(
        Conversation,
        conversation_id,
    )

    assert refreshed_conversation is not None

    assert refreshed_conversation.state is (original_state)

    assert refreshed_conversation.group_id == (original_group_id)

    assert refreshed_conversation.responsible_employee_id == original_owner_id

    assert refreshed_conversation.claimed_at == (original_claimed_at)
