"""Lifecycle-managed, at-least-once Outbox publisher."""

import asyncio
import logging
from contextlib import suppress


class OutboxPublisher:
    def __init__(self, control, interval: float = 1.0) -> None:
        self.control = control
        self.interval = interval
        self.task: asyncio.Task | None = None

    def start(self) -> None:
        if self.task is None or self.task.done():
            self.task = asyncio.create_task(self._run(), name="outbox-publisher")

    async def stop(self) -> None:
        if self.task:
            self.task.cancel()
            with suppress(asyncio.CancelledError):
                await self.task

    async def _run(self) -> None:
        while True:
            try:
                await self.control.dispatch_pending()
            except Exception as exc:
                # Do not log broker URLs or credentials embedded in exceptions.
                logging.getLogger(__name__).warning("outbox_dispatch_failed: %s", type(exc).__name__)
            await asyncio.sleep(self.interval)
