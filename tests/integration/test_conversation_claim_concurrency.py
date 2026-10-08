from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)

from app.db.models.conversation import (
    Conversation,
    ConversationState,
)
from app.db.session import create_session_factory
from app.repositories.conversation import (
    ConversationRepository,
)
from app.tenants.context import (
    TenantContext,
    TenantContextSource,
)

pytestmark = pytest.mark.integration


async def _prepare_conversation_table(
    *,
    engine: AsyncEngine,
    schema_name: str,
    tenant_id: UUID,
    conversation_id: UUID,
    group_id: UUID,
) -> None:
    session_factory = create_session_factory(engine)

    async with session_factory() as session:
        await session.execute(
            text(
                f"""
                CREATE SCHEMA "{schema_name}"
                """
            )
        )

        await session.execute(
            text(
                f"""
                CREATE TABLE "{schema_name}".conversations
                (
                    LIKE public.conversations
                    INCLUDING ALL
                )
                """
            )
        )

        await session.execute(
            text(
                f"""
                INSERT INTO "{schema_name}".conversations
                (
                    id,
                    tenant_id,
                    whatsapp_number_id,
                    customer_contact_id,
                    group_id,
                    state,
                    responsible_employee_id,
                    claimed_at,
                    created_at,
                    updated_at
                )
                VALUES
                (
                    :conversation_id,
                    :tenant_id,
                    :whatsapp_number_id,
                    :customer_contact_id,
                    :group_id,
                    'queued'::public.conversation_state,
                    NULL,
                    NULL,
                    now(),
                    now()
                )
                """
            ),
            {
                "conversation_id": conversation_id,
                "tenant_id": tenant_id,
                "whatsapp_number_id": uuid4(),
                "customer_contact_id": uuid4(),
                "group_id": group_id,
            },
        )

        await session.commit()


async def _drop_test_schema(
    *,
    engine: AsyncEngine,
    schema_name: str,
) -> None:
    session_factory = create_session_factory(engine)

    async with session_factory() as session:
        await session.execute(
            text(
                f"""
                DROP SCHEMA IF EXISTS "{schema_name}" CASCADE
                """
            )
        )

        await session.commit()


async def _claim_from_independent_session(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    schema_name: str,
    tenant: TenantContext,
    conversation_id: UUID,
    employee_id: UUID,
    ready: asyncio.Event,
    start: asyncio.Event,
) -> tuple[Conversation | None, int]:
    async with session_factory() as session:
        await session.execute(
            text(
                f"""
                SET LOCAL search_path
                TO "{schema_name}", public
                """
            )
        )

        backend_pid = await session.scalar(
            select(
                text("pg_backend_pid()"),
            )
        )

        assert backend_pid is not None

        ready.set()

        await start.wait()

        repository = ConversationRepository(
            session=session,
            tenant=tenant,
        )

        claimed = await repository.atomic_claim(
            tenant_id=tenant.tenant_id,
            conversation_id=conversation_id,
            employee_id=employee_id,
        )

        await session.commit()

        return claimed, int(backend_pid)


@pytest.mark.asyncio
async def test_two_concurrent_claims_have_exactly_one_winner(
    integration_engine: AsyncEngine,
) -> None:
    schema_name = f"claim_race_{uuid4().hex}"

    tenant_id = uuid4()
    conversation_id = uuid4()
    group_id = uuid4()

    employee_a_id = uuid4()
    employee_b_id = uuid4()

    tenant = TenantContext(
        tenant_id=tenant_id,
        slug="claim-race-tenant",
        source=TenantContextSource.AUTHENTICATED_SESSION,
    )

    await _prepare_conversation_table(
        engine=integration_engine,
        schema_name=schema_name,
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        group_id=group_id,
    )

    session_factory = create_session_factory(
        integration_engine,
    )

    ready_a = asyncio.Event()
    ready_b = asyncio.Event()
    start = asyncio.Event()

    try:
        task_a = asyncio.create_task(
            _claim_from_independent_session(
                session_factory=session_factory,
                schema_name=schema_name,
                tenant=tenant,
                conversation_id=conversation_id,
                employee_id=employee_a_id,
                ready=ready_a,
                start=start,
            )
        )

        task_b = asyncio.create_task(
            _claim_from_independent_session(
                session_factory=session_factory,
                schema_name=schema_name,
                tenant=tenant,
                conversation_id=conversation_id,
                employee_id=employee_b_id,
                ready=ready_b,
                start=start,
            )
        )

        await asyncio.gather(
            ready_a.wait(),
            ready_b.wait(),
        )

        start.set()

        result_a, result_b = await asyncio.gather(
            task_a,
            task_b,
        )

        claimed_a, backend_pid_a = result_a
        claimed_b, backend_pid_b = result_b

        assert backend_pid_a != backend_pid_b

        winners = [
            claimed
            for claimed in (
                claimed_a,
                claimed_b,
            )
            if claimed is not None
        ]

        losers = [
            claimed
            for claimed in (
                claimed_a,
                claimed_b,
            )
            if claimed is None
        ]

        assert len(winners) == 1
        assert len(losers) == 1

        async with session_factory() as verification_session:
            await verification_session.execute(
                text(
                    f"""
                    SET LOCAL search_path
                    TO "{schema_name}", public
                    """
                )
            )

            repository = ConversationRepository(
                session=verification_session,
                tenant=tenant,
            )

            conversation = await repository.get_by_id(
                conversation_id,
            )

            assert conversation is not None
            assert conversation.state is ConversationState.CLAIMED
            assert conversation.claimed_at is not None

            assert conversation.responsible_employee_id in {
                employee_a_id,
                employee_b_id,
            }

            assert conversation.responsible_employee_id == winners[0].responsible_employee_id

    finally:
        await _drop_test_schema(
            engine=integration_engine,
            schema_name=schema_name,
        )
