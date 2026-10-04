from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass

from sqlalchemy import text

from app.core.redis import create_redis_client
from app.db.session import create_database_engine
from app.integrations.rabbitmq.client import RabbitMQClient

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DependencyHealth:
    postgres: bool
    redis: bool
    rabbitmq: bool

    @property
    def required_dependencies_ready(self) -> bool:
        return self.postgres

    @property
    def all_dependencies_ready(self) -> bool:
        return self.postgres and self.redis and self.rabbitmq


class HealthChecker:
    def __init__(
        self,
        *,
        database_url: str | None,
        redis_url: str | None,
        rabbitmq_url: str | None,
        timeout_seconds: float = 3.0,
    ) -> None:
        self._database_url = database_url
        self._redis_url = redis_url
        self._rabbitmq_url = rabbitmq_url
        self._timeout_seconds = timeout_seconds

    @classmethod
    def from_environment(cls) -> HealthChecker:
        return cls(
            database_url=os.getenv("DATABASE_URL"),
            redis_url=os.getenv("REDIS_URL"),
            rabbitmq_url=os.getenv("RABBITMQ_URL"),
        )

    async def check(self) -> DependencyHealth:
        postgres, redis, rabbitmq = await asyncio.gather(
            self._check_postgres(),
            self._check_redis(),
            self._check_rabbitmq(),
        )

        return DependencyHealth(
            postgres=postgres,
            redis=redis,
            rabbitmq=rabbitmq,
        )

    async def _check_postgres(self) -> bool:
        if not self._database_url:
            return False

        engine = create_database_engine(self._database_url)

        try:
            async with asyncio.timeout(self._timeout_seconds):
                async with engine.connect() as connection:
                    await connection.execute(text("SELECT 1"))

            return True
        except Exception:
            logger.warning("PostgreSQL health check failed.")
            return False
        finally:
            await engine.dispose()

    async def _check_redis(self) -> bool:
        if not self._redis_url:
            return False

        client = create_redis_client(self._redis_url)

        try:
            async with asyncio.timeout(self._timeout_seconds):
                result = await client.ping()

            return bool(result)
        except Exception:
            logger.warning("Redis health check failed.")
            return False
        finally:
            await client.aclose()

    async def _check_rabbitmq(self) -> bool:
        if not self._rabbitmq_url:
            return False

        client = RabbitMQClient(self._rabbitmq_url)

        try:
            async with asyncio.timeout(self._timeout_seconds):
                await client.connect()

            return client.is_connected
        except Exception:
            logger.warning("RabbitMQ health check failed.")
            return False
        finally:
            await client.close()
