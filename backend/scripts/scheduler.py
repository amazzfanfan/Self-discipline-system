"""Run the durable APScheduler loop as a standalone process."""

from __future__ import annotations

import asyncio
import signal

from app.core.config import get_settings
from app.services.scheduler_service import scheduler, start_scheduler


async def main() -> None:
    settings = get_settings()
    if not settings.ENABLE_SCHEDULER:
        raise RuntimeError("ENABLE_SCHEDULER must be true")

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()

    def request_stop(*_: object) -> None:
        loop.call_soon_threadsafe(stop.set)

    for signal_name in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(signal_name, request_stop)
        except (NotImplementedError, RuntimeError):
            signal.signal(signal_name, request_stop)

    start_scheduler()
    try:
        await stop.wait()
    finally:
        if scheduler.running:
            scheduler.shutdown(wait=False)


if __name__ == "__main__":
    asyncio.run(main())
