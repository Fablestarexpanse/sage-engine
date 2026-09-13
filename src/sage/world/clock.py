"""Coarse world day cycle — morning/day/evening/night from wall time.

One island day = 40 real minutes (10 per phase): fast enough to watch a full
day during a test session, slow enough that routines feel like routines.
"""

import time

DAY_SECONDS = 40 * 60
PHASES = ("morning", "day", "evening", "night")


def day_phase(now: float | None = None) -> str:
    t = time.time() if now is None else now
    slot = int((t % DAY_SECONDS) / (DAY_SECONDS / len(PHASES)))
    return PHASES[min(slot, len(PHASES) - 1)]
