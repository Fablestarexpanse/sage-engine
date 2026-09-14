"""Durable agent state in the plugin's own table, plg_agents_state (keyed by persona id)."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, String, delete, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from sage.api import PluginAPI

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


class AgentStateRow(Base):
    __tablename__ = "plg_agents_state"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)  # persona id
    name: Mapped[str] = mapped_column(String(100), index=True)
    room_id: Mapped[str] = mapped_column(String(255))
    stats: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    inventory: Mapped[list[Any]] = mapped_column(JSON, default=list)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class AgentStore:
    def __init__(self, api: PluginAPI):
        self.api = api

    async def load(self, persona_id: str) -> dict[str, Any] | None:
        try:
            async with self.api.persistence.session() as db:
                row = (
                    await db.execute(select(AgentStateRow).where(AgentStateRow.id == persona_id))
                ).scalar_one_or_none()
                if row is None:
                    return None
                return {
                    "stats": dict(row.stats or {}),
                    "inventory": list(row.inventory or []),
                    "room_id": row.room_id,
                }
        except Exception:
            logger.exception("Agent state load failed for %s", persona_id)
            return None

    async def delete(self, persona_id: str) -> None:
        try:
            async with self.api.persistence.session() as db, db.begin():
                await db.execute(delete(AgentStateRow).where(AgentStateRow.id == persona_id))
        except Exception:
            logger.exception("Agent state delete failed for %s", persona_id)

    async def save(self, rows: list[dict[str, Any]]) -> None:
        """Upsert {id, name, room_id, stats, inventory} rows in one transaction."""
        if not rows:
            return
        try:
            async with self.api.persistence.session() as db, db.begin():
                for data in rows:
                    row = (
                        await db.execute(
                            select(AgentStateRow).where(AgentStateRow.id == data["id"])
                        )
                    ).scalar_one_or_none()
                    if row is None:
                        row = AgentStateRow(id=data["id"], name=data["name"])
                        db.add(row)
                    row.name = data["name"]
                    row.room_id = data["room_id"]
                    row.stats = data["stats"]
                    row.inventory = data["inventory"]
                    row.updated_at = datetime.utcnow()
        except Exception:
            logger.exception("Agent state flush failed")
