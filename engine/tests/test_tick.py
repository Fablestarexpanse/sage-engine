"""TickManager — loop counting, handler dispatch, and stop()."""

from __future__ import annotations

import asyncio
import unittest

from sage.core.tick import TickManager


class TestTickManager(unittest.TestCase):
    def test_handlers_called_each_tick(self) -> None:
        asyncio.run(self._handlers_called())

    async def _handlers_called(self) -> None:
        tm = TickManager(tick_rate=0.01)
        calls: list[int] = []

        async def counter(tick: int) -> None:
            calls.append(tick)
            if len(calls) >= 3:
                tm.stop()

        tm.register(counter)
        await asyncio.wait_for(tm.run(), timeout=2.0)
        self.assertGreaterEqual(len(calls), 3)
        self.assertEqual(calls[:3], [1, 2, 3])
        self.assertEqual(tm.tick_count, calls[-1])

    def test_stop_halts_loop(self) -> None:
        asyncio.run(self._stop_halts())

    async def _stop_halts(self) -> None:
        tm = TickManager(tick_rate=0.01)

        async def stopper(tick: int) -> None:
            tm.stop()

        tm.register(stopper)
        await asyncio.wait_for(tm.run(), timeout=2.0)
        self.assertFalse(tm.is_running)
        self.assertEqual(tm.tick_count, 1)

    def test_handler_exception_does_not_kill_loop(self) -> None:
        asyncio.run(self._exception_survives())

    async def _exception_survives(self) -> None:
        tm = TickManager(tick_rate=0.01)
        good_calls: list[int] = []

        async def bad(tick: int) -> None:
            raise RuntimeError("boom")

        async def good(tick: int) -> None:
            good_calls.append(tick)
            if len(good_calls) >= 2:
                tm.stop()

        tm.register(bad)
        tm.register(good)
        await asyncio.wait_for(tm.run(), timeout=2.0)
        self.assertGreaterEqual(len(good_calls), 2)

    def test_handler_exception_is_logged_with_handler_name(self) -> None:
        asyncio.run(self._exception_logged())

    async def _exception_logged(self) -> None:
        tm = TickManager(tick_rate=0.01)

        async def exploding_job(tick: int) -> None:
            tm.stop()
            raise RuntimeError("boom")

        tm.register(exploding_job)
        with self.assertLogs("sage.core.tick", level="ERROR") as logs:
            await asyncio.wait_for(tm.run(), timeout=2.0)
        text = "\n".join(logs.output)
        self.assertIn("exploding_job", text)
        self.assertIn("boom", text)

    def test_repeated_handler_error_logged_once(self) -> None:
        asyncio.run(self._repeat_quiet())

    async def _repeat_quiet(self) -> None:
        tm = TickManager(tick_rate=0.001)

        async def broken_every_tick(tick: int) -> None:
            if tick >= 5:
                tm.stop()
            raise RuntimeError("same")

        tm.register(broken_every_tick)
        with self.assertLogs("sage.core.tick", level="ERROR") as logs:
            await asyncio.wait_for(tm.run(), timeout=2.0)
        failures = [line for line in logs.output if "broken_every_tick" in line]
        self.assertEqual(len(failures), 1)

    def test_run_with_no_handlers(self) -> None:
        asyncio.run(self._no_handlers())

    async def _no_handlers(self) -> None:
        tm = TickManager(tick_rate=0.01)

        async def stop_soon() -> None:
            await asyncio.sleep(0.05)
            tm.stop()

        await asyncio.wait_for(asyncio.gather(tm.run(), stop_soon()), timeout=2.0)
        self.assertGreater(tm.tick_count, 0)


if __name__ == "__main__":
    unittest.main()
