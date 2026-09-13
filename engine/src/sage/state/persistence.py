"""PersistenceManager — flushes Redis player state to Postgres every ~60 s on tick."""

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import select

from sage.state.models import Character

if TYPE_CHECKING:
    from sage.server import SageServer

logger = logging.getLogger(__name__)


class PersistenceManager:
    """
    Handles syncing high-frequency Redis state to persistent PostgreSQL storage.
    """

    def __init__(self, server: "SageServer"):
        self.server = server
        self.flush_interval_ticks = 240  # Every 60 seconds at 4Hz
        # Plugins persisting their own characters on the same cadence (api.persistence).
        self.flush_hooks: list = []

    async def flush_all(self):
        """Perform a full synchronization of active world state/players."""
        logger.info("Persistence: Starting background flush to PostgreSQL...")
        try:
            for player_id in await self.server.redis.get_all_active_player_ids():
                await self.sync_character(player_id)
            for hook in list(self.flush_hooks):
                try:
                    await hook()
                except Exception:
                    logger.exception("Persistence: flush hook %s failed", hook)
        except Exception:
            logger.exception("Persistence: flush_all failed; game loop continues")
            return
        logger.info("Persistence: Flush complete.")

    async def sync_character(self, player_id: str):
        """Sync a single character's Redis state (location, stats, inventory) to the DB."""
        try:
            current_room = await self.server.redis.get_player_location(player_id)
            current_stats = await self.server.redis.get_player_stats(player_id)
            current_inventory = await self.server.redis.get_player_inventory(player_id)

            async with self.server.db.session_factory() as session:
                async with session.begin():
                    result = await session.execute(
                        select(Character).where(Character.name == player_id)
                    )
                    character = result.scalar_one_or_none()

                    if character:
                        if current_room:
                            character.room_id = current_room
                        if current_stats:
                            character.stats = current_stats
                            # The wallet spends from the stats blob; mirror the primary
                            # balance to the account-visible column.
                            wallet = self.server.wallet
                            if wallet.enabled and isinstance(current_stats.get(wallet.key()), int):
                                character.digi_balance = current_stats[wallet.key()]
                        if current_inventory is not None:
                            character.inventory = current_inventory
                        character.updated_at = datetime.utcnow()
                        logger.debug(f"Synced character {player_id} to DB.")
        except Exception:
            logger.exception("Persistence: sync_character failed for %s", player_id)

    async def on_tick(self, tick_count: int):
        """Periodic background task triggered by the TickManager."""
        if tick_count % self.flush_interval_ticks == 0:
            await self.flush_all()
