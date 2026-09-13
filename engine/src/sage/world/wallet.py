"""In-world wallet: balances of the world's currencies (``currencies.yaml``), kept in the stats blob.

The engine knows *that* characters carry money, never *which* money. The first currency a world
declares is its primary one; callers that don't name a currency use it. A balance lives in the
character's stats blob under the currency key, so it travels with Redis hot state like any stat.

Durability: until the JSONB state step of the phase-3 plan, the primary balance is mirrored to the
character's legacy wallet column on login and flush (``server._bootstrap_session``,
``PersistenceManager``).

Out-of-world AI-art credit is a separate engine ledger (``EconomyService``), not a currency here.
"""

from __future__ import annotations

from typing import Any

from sage import lexicon


class WalletError(ValueError):
    """A wallet call named a currency the world does not declare, or a negative amount."""


class Wallet:
    def __init__(self, world: Any):
        self._world = world

    def _currency(self, key: str | None) -> Any:
        currencies = list(getattr(self._world, "currencies", []) or [])
        if key is None:
            if not currencies:
                raise WalletError(f"world {self._world.id!r} declares no currencies")
            return currencies[0]
        for currency in currencies:
            if currency.key == key:
                return currency
        raise WalletError(f"world {self._world.id!r} has no currency {key!r}")

    @property
    def enabled(self) -> bool:
        return bool(getattr(self._world, "currencies", None))

    def key(self, key: str | None = None) -> str:
        return self._currency(key).key

    def name(self, key: str | None = None) -> str:
        """The currency's player-facing name, through the lexicon (live-editable)."""
        currency = self._currency(key)
        return lexicon.t(currency.label)

    def starting(self, key: str | None = None) -> int:
        return int(self._currency(key).starting)

    def balance(self, stats: dict[str, Any], key: str | None = None) -> int:
        if not self.enabled:
            return 0
        return int(stats.get(self.key(key), 0) or 0)

    def set(self, stats: dict[str, Any], amount: int, key: str | None = None) -> int:
        """Set a balance outright (bootstrap, admin tools); never below zero."""
        stats[self.key(key)] = max(0, int(amount))
        return stats[self.key(key)]

    def credit(self, stats: dict[str, Any], amount: int, key: str | None = None) -> int:
        if int(amount) < 0:
            raise WalletError(f"credit amount must be >= 0, got {amount}")
        return self.set(stats, self.balance(stats, key) + int(amount), key)

    def debit(self, stats: dict[str, Any], amount: int, key: str | None = None) -> bool:
        """Take amount if the character can cover it; False (and nothing taken) otherwise."""
        if int(amount) < 0:
            raise WalletError(f"debit amount must be >= 0, got {amount}")
        have = self.balance(stats, key)
        if have < int(amount):
            return False
        self.set(stats, have - int(amount), key)
        return True

    def take_up_to(self, stats: dict[str, Any], amount: int, key: str | None = None) -> int:
        """Take as much of amount as the character has (bills); returns what was taken."""
        taken = max(0, min(self.balance(stats, key), int(amount)))
        self.set(stats, self.balance(stats, key) - taken, key)
        return taken
