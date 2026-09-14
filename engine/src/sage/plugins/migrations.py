"""Core and plugin-owned database migrations (docs/sage/PHASE1_CONTRACTS.md D.D).

The core chain carries the branch label ``sage_core``. A plugin with tables ships
``migrations/versions/`` whose base revision has ``branch_labels = ("plg_<id>",)``,
``down_revision = None`` and ``depends_on`` a core revision. Plugin tables are named
``plg_<id>_*``. The server refuses to start while any enabled branch has unapplied revisions;
``python -m sage db upgrade`` applies them and ``python -m sage plugin uninstall`` removes a
plugin's branch (dropping its tables).
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine

import sage
from alembic.config import Config as AlembicConfig
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory

ENGINE_DIR = Path(sage.__file__).resolve().parents[2]
CORE_TABLE_EXEMPT = {"alembic_version"}


def plugin_migration_dir(plugin_path: Path) -> Path | None:
    versions = Path(plugin_path) / "migrations" / "versions"
    return versions if versions.is_dir() else None


def alembic_config(plugin_paths: Iterable[Path] = ()) -> AlembicConfig:
    """Alembic config covering the core chain plus each given plugin's migrations."""
    cfg = AlembicConfig(str(ENGINE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(ENGINE_DIR / "alembic"))
    locations = [ENGINE_DIR / "alembic" / "versions"]
    locations += [d for p in plugin_paths if (d := plugin_migration_dir(p)) is not None]
    import os

    cfg.set_main_option("version_locations", os.pathsep.join(str(p) for p in locations))
    return cfg


def plugin_branch(plugin_id: str) -> str:
    return f"plg_{plugin_id}"


async def _run(database_url: str, fn: Callable[[Any], Any]) -> Any:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as conn:
            return await conn.run_sync(fn)
    finally:
        await engine.dispose()


async def pending_heads_async(cfg: AlembicConfig, database_url: str) -> list[str]:
    """Script heads not yet applied to the database (empty when fully migrated)."""
    script = ScriptDirectory.from_config(cfg)

    def current(conn) -> tuple[str, ...]:
        return MigrationContext.configure(conn).get_current_heads()

    applied: set[str] = set()
    for head in await _run(database_url, current):
        applied.update(rev.revision for rev in script.iterate_revisions(head, "base"))
    return sorted(h for h in script.get_heads() if h not in applied)


def pending_heads(cfg: AlembicConfig, database_url: str) -> list[str]:
    return asyncio.run(pending_heads_async(cfg, database_url))


async def unexpected_tables_async(
    database_url: str, core_tables: Iterable[str], plugin_ids: Iterable[str]
) -> list[str]:
    """Tables that are neither core, alembic's, nor named plg_<known plugin>_*."""
    allowed = set(core_tables) | CORE_TABLE_EXEMPT
    prefixes = tuple(f"plg_{pid}_" for pid in plugin_ids)
    names = await _run(database_url, lambda conn: inspect(conn).get_table_names())
    return sorted(
        n for n in names if n not in allowed and not (prefixes and n.startswith(prefixes))
    )


def is_core_object(obj: Any, name: str, type_: str, reflected: bool, compare_to: Any) -> bool:
    """Autogenerate filter: plugin tables belong to their plugins' migrations."""
    return not (type_ == "table" and re.match(r"^plg_[a-z][a-z0-9_]*_", name or ""))
