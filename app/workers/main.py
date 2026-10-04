from __future__ import annotations

import asyncio
import os
import signal

from app.integrations.rabbitmq.client import RabbitMQClient


async def run_worker() -> None:
    rabbitmq_url = os.getenv("RABBITMQ_URL")

    if not rabbitmq_url:
        raise RuntimeError("RABBITMQ_URL is required to start the worker.")

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def request_shutdown() -> None:
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(
                sig,
                request_shutdown,
            )
        except NotImplementedError:
            signal.signal(
                sig,
                lambda *_: loop.call_soon_threadsafe(request_shutdown),
            )

    rabbitmq = RabbitMQClient(rabbitmq_url)

    await rabbitmq.connect()

    try:
        print("Worker started. RabbitMQ connection established.")

        await stop_event.wait()
    finally:
        print("Worker shutting down...")

        await rabbitmq.close()

        print("Worker stopped.")


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
