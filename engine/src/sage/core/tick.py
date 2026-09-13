"""TickManager — drives the 4 Hz game loop with drift compensation."""

import asyncio
import logging
import time
from collections.abc import Callable, Coroutine
from typing import Any

logger = logging.getLogger(__name__)


class TickManager:
    """
    Manages the game heart beat with a fixed timestep.
    Ensures logic runs at a consistent rate regardless of processing time.
    """

    # Same handler + same error is logged at most once per this many ticks (~60 s at 4 Hz).
    ERROR_REPEAT_TICKS = 240

    def __init__(self, tick_rate: float = 0.25):
        self.tick_rate = tick_rate
        self.tick_count = 0
        self.is_running = False
        self._handlers: list[Callable[[int], Coroutine[Any, Any, None]]] = []
        self._last_error_tick: dict[tuple[str, str], int] = {}

    def register(self, handler: Callable[[int], Coroutine[Any, Any, None]]) -> None:
        """Register an async handler to be called each tick."""
        self._handlers.append(handler)

    def every(
        self,
        seconds: float,
        job: Callable[[int], Coroutine[Any, Any, None]],
        name: str | None = None,
    ) -> Callable[[int], Coroutine[Any, Any, None]]:
        """Run an async job about every `seconds` (rounded to whole ticks, at least one).

        Returns the registered wrapper; its __qualname__ is `name` so failures log clearly.
        """
        interval = max(1, round(seconds / self.tick_rate))

        async def run_job(tick: int) -> None:
            if tick % interval == 0:
                await job(tick)

        run_job.__qualname__ = name or getattr(job, "__qualname__", "tick_job")
        self._handlers.append(run_job)
        return run_job

    def unregister(self, handler: Callable[[int], Coroutine[Any, Any, None]]) -> None:
        if handler in self._handlers:
            self._handlers.remove(handler)

    async def run(self) -> None:
        """Main tick loop with drift compensation."""
        self.is_running = True
        logger.info(f"TickManager started at {1 / self.tick_rate}Hz ({self.tick_rate}s interval)")

        while self.is_running:
            start_time = time.monotonic()
            self.tick_count += 1

            # Execute all handlers for this tick
            handlers = list(self._handlers)
            tasks = [asyncio.create_task(handler(self.tick_count)) for handler in handlers]
            if tasks:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for handler, result in zip(handlers, results, strict=True):
                    if isinstance(result, Exception):
                        self._log_handler_error(handler, result)

            # Compensation for processing time
            elapsed = time.monotonic() - start_time
            sleep_time = max(0, self.tick_rate - elapsed)

            if elapsed > self.tick_rate:
                logger.warning(
                    f"Tick {self.tick_count} took {elapsed:.4f}s - exceeding rate of {self.tick_rate}s!"
                )

            await asyncio.sleep(sleep_time)

    def _log_handler_error(self, handler: Callable[..., Any], exc: Exception) -> None:
        """Log a failed tick handler; repeats of the same error stay quiet for ERROR_REPEAT_TICKS."""
        name = getattr(handler, "__qualname__", repr(handler))
        key = (name, repr(exc))
        last = self._last_error_tick.get(key)
        if last is not None and self.tick_count - last < self.ERROR_REPEAT_TICKS:
            return
        self._last_error_tick[key] = self.tick_count
        logger.error(
            "Tick handler %s failed on tick %d: %r",
            name,
            self.tick_count,
            exc,
            exc_info=(type(exc), exc, exc.__traceback__),
        )

    def stop(self) -> None:
        """Stop the tick loop."""
        self.is_running = False
