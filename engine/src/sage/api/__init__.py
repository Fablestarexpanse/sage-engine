"""The stable surface plugins import (docs/sage/PHASE1_CONTRACTS.md C.1).

Plugins import from ``sage.api`` only. Everything else under ``sage.*`` is engine-internal and
may change without notice; an import-boundary check enforces this once plugins exist in-tree.
"""

from sage.core.events import (
    CommandExecuted,
    CountersChanged,
    EntityKilled,
    Event,
    PlayerDied,
    RoomEntered,
    SessionEnded,
    SessionStarted,
)
from sage.lexicon import t
from sage.plugins.api import PluginAPI
from sage.plugins.manifest import PluginError
from sage.telemetry import log_event
from sage.world.death import Respawn
from sage.world.wallet import Wallet, WalletError

__all__ = [
    "CommandExecuted",
    "CountersChanged",
    "EntityKilled",
    "Event",
    "PlayerDied",
    "PluginAPI",
    "PluginError",
    "Respawn",
    "RoomEntered",
    "SessionEnded",
    "SessionStarted",
    "Wallet",
    "WalletError",
    "log_event",
    "t",
]
