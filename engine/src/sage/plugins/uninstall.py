"""Remove a plugin from a world: its schema, optionally its character state, its manifest entry."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from alembic import command
from sage.plugins.loader import PluginRecord
from sage.plugins.manifest import PluginError
from sage.plugins.migrations import alembic_config, plugin_branch, plugin_migration_dir


def dependents(records: list[PluginRecord], plugin_id: str) -> list[str]:
    return sorted(
        r.id
        for r in records
        if plugin_id in r.manifest.depends and not r.manifest.depends[plugin_id].optional
    )


async def purge_state_blocks(database_url: str, blocks: list[str]) -> int:
    """Delete the named state blocks from every character and agent stats blob."""
    from sage.state.models import AgentState, Character

    engine = create_async_engine(database_url)
    changed = 0
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        async with factory() as session, session.begin():
            for model in (Character, AgentState):
                for row in (await session.execute(select(model))).scalars():
                    stats = dict(row.stats or {})
                    if any(block in stats for block in blocks):
                        for block in blocks:
                            stats.pop(block, None)
                        row.stats = stats
                        changed += 1
    finally:
        await engine.dispose()
    return changed


def remove_from_world_manifest(world_toml: Path, plugin_id: str) -> bool:
    """Drop `plugin_id = ...` from the [plugins] table, keeping every other line and comment."""
    lines = Path(world_toml).read_text(encoding="utf-8").splitlines(keepends=True)
    out, section, removed = [], None, False
    for line in lines:
        header = re.match(r"^\s*\[([^\]]+)\]", line)
        if header:
            section = header.group(1).strip()
        if section == "plugins" and re.match(rf"^\s*{re.escape(plugin_id)}\s*=", line):
            removed = True
            continue
        out.append(line)
    Path(world_toml).write_text("".join(out), encoding="utf-8")
    return removed


async def uninstall_plugin(
    world: Any,
    records: list[PluginRecord],
    plugin_id: str,
    database_url: str,
    *,
    purge_state: bool = False,
) -> list[str]:
    record = next((r for r in records if r.id == plugin_id), None)
    if record is None:
        raise PluginError(f"plugin {plugin_id!r} is not enabled in world {world.id!r}")
    blockers = dependents(records, plugin_id)
    if blockers:
        raise PluginError(f"cannot uninstall {plugin_id}: required by {', '.join(blockers)}")

    report = []
    if plugin_migration_dir(record.path) is not None:
        import asyncio

        cfg = alembic_config([r.path for r in records])
        # alembic's env.py runs its own event loop, so the downgrade runs on a worker thread.
        await asyncio.to_thread(command.downgrade, cfg, f"{plugin_branch(plugin_id)}@base")
        report.append(f"downgraded {plugin_branch(plugin_id)} to base (plugin tables dropped)")
    if purge_state and record.manifest.touches.state_blocks:
        count = await purge_state_blocks(database_url, record.manifest.touches.state_blocks)
        report.append(
            f"removed state blocks {record.manifest.touches.state_blocks} from {count} rows"
        )
    if remove_from_world_manifest(world.root / "world.toml", plugin_id):
        report.append(f"removed {plugin_id} from {world.root / 'world.toml'} [plugins]")
    return report
