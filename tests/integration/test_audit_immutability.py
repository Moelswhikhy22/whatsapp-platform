from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import (
    text,
)
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import (
    create_async_engine,
)


pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_audit_tables_have_immutability_triggers() -> None:
    engine = create_async_engine(os.environ["TEST_DATABASE_URL"])

    try:
        async with engine.connect() as connection:
            result = await connection.execute(
                text(
                    """
                    SELECT tgname
                    FROM pg_trigger
                    WHERE NOT tgisinternal
                      AND tgname IN (
                        'trg_business_audit_logs_immutable',
                        'trg_platform_audit_logs_immutable',
                        'trg_security_access_logs_immutable'
                      )
                    ORDER BY tgname
                    """
                )
            )

            trigger_names = {row[0] for row in result}

        assert trigger_names == {
            "trg_business_audit_logs_immutable",
            "trg_platform_audit_logs_immutable",
            "trg_security_access_logs_immutable",
        }

    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_platform_audit_row_cannot_be_updated_or_deleted() -> None:
    engine = create_async_engine(os.environ["TEST_DATABASE_URL"])

    audit_id = uuid4()

    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()

            try:
                await connection.execute(
                    text(
                        """
                        INSERT INTO platform_audit_logs (
                            id,
                            actor_type,
                            actor_id,
                            action,
                            trace_id
                        )
                        VALUES (
                            :id,
                            'system',
                            'immutability-test',
                            'audit.immutability_test',
                            :trace_id
                        )
                        """
                    ),
                    {
                        "id": audit_id,
                        "trace_id": (uuid4().hex),
                    },
                )

                update_savepoint = await connection.begin_nested()

                with pytest.raises(DBAPIError):
                    await connection.execute(
                        text(
                            """
                            UPDATE platform_audit_logs
                            SET action = 'tampered'
                            WHERE id = :id
                            """
                        ),
                        {
                            "id": audit_id,
                        },
                    )

                await update_savepoint.rollback()

                delete_savepoint = await connection.begin_nested()

                with pytest.raises(DBAPIError):
                    await connection.execute(
                        text(
                            """
                            DELETE FROM platform_audit_logs
                            WHERE id = :id
                            """
                        ),
                        {
                            "id": audit_id,
                        },
                    )

                await delete_savepoint.rollback()

            finally:
                await transaction.rollback()

    finally:
        await engine.dispose()
