"""Achievements as a plugin: engine counters -> CountersChanged -> grants and announcements."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from sage.world.counters import count, count_for_player, note_visit, visit_for_player
from tests.fakes import StubSession, repo_world
from tests.plugins.conftest import server_for


def _plugin_module(name: str):
    return sys.modules[f"sage_plugins.achievements.sage_plugin_achievements.{name}"]


def _write(content_dir: Path, **files: str) -> None:
    d = content_dir / "achievements"
    d.mkdir(parents=True, exist_ok=True)
    for stem, body in files.items():
        (d / f"{stem}.yaml").write_text(body, encoding="utf-8")


def test_counters_grant_and_announce(plugin_host):
    host = plugin_host(repo_world(), ["achievements"])
    server = server_for(host)
    stats: dict = {}

    async def kill():
        return await count(server, "hero", stats, "kills", "kills.scrap_drone")

    lines = asyncio.run(kill())
    assert stats["counters"] == {"kills": 1, "kills.scrap_drone": 1}
    assert any("Achievement unlocked" in line and "First Blood" in line for line in lines), lines
    assert "first_blood" in stats["achievements"]
    again = asyncio.run(kill())
    assert not any("First Blood" in line for line in again)  # granted once


def test_grant_rules_all_any_and_unrelated_counters(plugin_host):
    host = plugin_host(repo_world(), ["achievements"])
    main = _plugin_module("main")
    models = _plugin_module("models")
    registry_mod = _plugin_module("registry")
    both = models.AchievementModel(
        id="both", name="Both", story="did both", criteria={"a": 1, "b": 1}
    )
    either = models.AchievementModel(
        id="either", name="Either", story="did one", criteria={"a": 1, "b": 1}, match="any"
    )
    registry = registry_mod.AchievementRegistry([both, either])
    stats = {"counters": {"a": 1}}
    assert [a.id for a in main.check_grants(stats, registry, ["a"], now=1)] == ["either"]
    stats["counters"]["b"] = 1
    assert [a.id for a in main.check_grants(stats, registry, ["b"], now=2)] == ["both"]
    assert main.check_grants({"counters": {"c": 5}}, registry, ["c"]) == []
    assert host.loaded[0].id == "achievements"


def test_definitions_reload_when_files_change(plugin_host, tmp_path):
    world = repo_world()
    content = tmp_path / "content"
    _write(content, one="name: One\nstory: did a thing\ncriteria:\n  pokes: 1\n")
    main = None
    host = plugin_host(world, ["achievements"])
    main = _plugin_module("main")
    cache = main._CachedRegistry(content / "achievements")
    assert [a.id for a in cache.get().all()] == ["one"]
    _write(content, two="name: Two\nstory: did two\ncriteria:\n  pokes: 2\n")
    assert [a.id for a in cache.get().all()] == ["one", "two"]
    assert host is not None


def test_room_visits_count_once_and_unlock(plugin_host):
    host = plugin_host(repo_world(), ["achievements"])
    server = server_for(host)
    stats: dict = {}
    assert note_visit(stats, "z:a") is True
    assert note_visit(stats, "z:a") is False
    assert stats["counters"]["rooms_visited"] == 1

    async def walk():
        await host.redis.set_player_stats("hero", {})
        lines: list[str] = []
        for i in range(12):
            lines += await visit_for_player(server, "hero", f"z:room{i}")
        lines += await visit_for_player(server, "hero", "z:room0")  # revisit: nothing
        return lines, await host.redis.get_player_stats("hero")

    lines, saved = asyncio.run(walk())
    assert saved["counters"]["rooms_visited"] == 12
    assert len(saved["visited_rooms"]) == 12
    assert lines == [] or all("Achievement unlocked" in line for line in lines)


def test_achievements_command_lists_grants(plugin_host):
    host = plugin_host(repo_world(), ["achievements"])
    server = server_for(host)

    async def run():
        await host.redis.set_player_stats("hero", {})
        await count_for_player(server, "hero", "kills")
        session = StubSession("hero")
        await host.registry.get("ach").handler(session, [])
        await host.registry.get("achievements").handler(session, ["all"])
        return session.sent

    earned, everything = asyncio.run(run())
    assert earned.startswith("Achievements (1/") and "First Blood" in earned
    assert everything.startswith("All achievements:") and "[X]" in everything


def test_engine_counts_without_the_plugin():
    """A world without achievements still counts; nothing is announced."""
    from types import SimpleNamespace

    from sage.core.events import EventBus

    stats: dict = {}
    lines = asyncio.run(count(SimpleNamespace(events=EventBus()), "hero", stats, "kills"))
    assert lines == [] and stats == {"counters": {"kills": 1}}
