"""Live lexicon edits from Nexus, versioned with rollback (decision 7, contracts B.5/B.7).

Every save is a new ``world_overrides`` row; the newest save becomes the active version.
Rollback re-activates an older version; clearing deactivates them all so the world package
value shows through again. History is never deleted.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select, update

from sage.state.models import WorldOverride

KIND_LEXICON = "lexicon"


class OverrideError(ValueError):
    """Unknown key or version."""


class LexiconOverrides:
    def __init__(self, session_factory: Any):
        self._sessions = session_factory

    async def active(self) -> dict[str, str]:
        async with self._sessions() as session:
            rows = await session.execute(
                select(WorldOverride.key, WorldOverride.value).where(
                    WorldOverride.kind == KIND_LEXICON, WorldOverride.active.is_(True)
                )
            )
            return {key: str(value) for key, value in rows.all()}

    async def history(self, key: str) -> list[dict[str, Any]]:
        async with self._sessions() as session:
            rows = await session.execute(
                select(WorldOverride)
                .where(WorldOverride.kind == KIND_LEXICON, WorldOverride.key == key)
                .order_by(WorldOverride.version.desc())
            )
            return [
                {
                    "version": row.version,
                    "value": row.value,
                    "active": row.active,
                    "author_staff_id": row.author_staff_id,
                    "note": row.note,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                }
                for row in rows.scalars()
            ]

    async def save(
        self, key: str, value: str, author_staff_id: int | None, note: str | None = None
    ) -> int:
        async with self._sessions() as session, session.begin():
            latest = await session.scalar(
                select(func.max(WorldOverride.version)).where(
                    WorldOverride.kind == KIND_LEXICON, WorldOverride.key == key
                )
            )
            version = int(latest or 0) + 1
            await self._deactivate(session, key)
            session.add(
                WorldOverride(
                    kind=KIND_LEXICON,
                    key=key,
                    version=version,
                    value=value,
                    active=True,
                    author_staff_id=author_staff_id,
                    note=note,
                    created_at=datetime.utcnow(),
                )
            )
            return version

    async def rollback(self, key: str, version: int) -> None:
        async with self._sessions() as session, session.begin():
            row = await session.scalar(
                select(WorldOverride).where(
                    WorldOverride.kind == KIND_LEXICON,
                    WorldOverride.key == key,
                    WorldOverride.version == version,
                )
            )
            if row is None:
                raise OverrideError(f"{key!r} has no version {version}")
            await self._deactivate(session, key)
            row.active = True

    async def clear(self, key: str) -> None:
        async with self._sessions() as session, session.begin():
            await self._deactivate(session, key)

    async def _deactivate(self, session: Any, key: str) -> None:
        await session.execute(
            update(WorldOverride)
            .where(WorldOverride.kind == KIND_LEXICON, WorldOverride.key == key)
            .values(active=False)
        )
