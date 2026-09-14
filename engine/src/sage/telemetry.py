"""World telemetry — append-only JSONL event log + Redis heatmaps.

Built for overnight soak runs: every interesting thing an agent or player
does lands as one JSON line in logs/events-YYYYMMDD.jsonl (greppable,
pandas-able), and hot aggregates (room presence, kills, deaths, trades)
accumulate in Redis hashes for instant heatmaps.

All writes are best-effort: telemetry must never break the game loop.
"""

import json
import logging
import time
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

LOG_DIR = Path("logs")

_handles: dict[str, object] = {}
# Tests must never write into the live soak log (set by tests/conftest.py).
_disabled = False


def disable() -> None:
    global _disabled
    _disabled = True


def _handle():
    day = datetime.now().strftime("%Y%m%d")
    key = f"events-{day}"
    fh = _handles.get(key)
    if fh is None:
        try:
            LOG_DIR.mkdir(exist_ok=True)
            # Close yesterday's handle on rollover.
            for old_key, old_fh in list(_handles.items()):
                try:
                    old_fh.close()
                except Exception:
                    pass
                _handles.pop(old_key, None)
            fh = open(LOG_DIR / f"{key}.jsonl", "a", encoding="utf-8", buffering=1)
            _handles[key] = fh
        except Exception:
            logger.debug("telemetry file open failed", exc_info=True)
            return None
    return fh


def log_event(kind: str, /, **fields) -> None:
    """One JSONL line: {"t": epoch, "kind": ..., **fields}. Never raises.

    `kind` is positional-only so a field that happens to be called "kind"
    can't collide at call time (that crashed buy/sell for a whole night).
    """
    if _disabled:
        return
    try:
        fh = _handle()
        if fh is None:
            return
        record = {**fields, "t": round(time.time(), 2), "kind": kind}
        fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    except Exception:
        logger.debug("telemetry write failed", exc_info=True)


async def heat(redis, map_name: str, key: str, by: int = 1) -> None:
    """Increment a heatmap cell: hash heat:<map_name>[key] += by. Never raises."""
    if _disabled:
        return
    try:
        await redis.client.hincrby(redis.key(f"heat:{map_name}"), key, by)
    except Exception:
        logger.debug("heatmap incr failed", exc_info=True)


async def read_heatmaps(redis, names: list[str]) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for name in names:
        try:
            raw = await redis.client.hgetall(redis.key(f"heat:{name}"))
            out[name] = {
                (k.decode() if isinstance(k, bytes) else k): int(v) for k, v in (raw or {}).items()
            }
        except Exception:
            out[name] = {}
    return out
