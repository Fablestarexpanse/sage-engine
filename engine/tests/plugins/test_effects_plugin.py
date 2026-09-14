"""Effects plugin through the host: rest in safe rooms, ticks advance, a fatal tick ends the session."""

import asyncio
from types import SimpleNamespace

from sage.effects.engine import apply_effect, make_effect
from tests.fakes import StubSession, repo_world

ROOMS = {
    "inn": "id: town:inn\nzone: town\ntype: safe\n",
    "alley": "id: town:alley\nzone: town\ntype: hub\n",
}


def _host(plugin_host, tmp_path, session):
    rooms = tmp_path / "content" / "world" / "zones" / "town" / "rooms"
    rooms.mkdir(parents=True)
    for slug, body in ROOMS.items():
        (rooms / f"{slug}.yaml").write_text(body, encoding="utf-8")
    world = repo_world()
    manifest = world.manifest.model_copy(deep=True)
    content_override = tmp_path / "content"
    pushed: list = []

    async def push(s):
        pushed.append(s.player_id)

    server = SimpleNamespace(
        session_manager=SimpleNamespace(
            player_to_session={"hero": "s1"},
            get_session_by_player=lambda pid: session if pid == "hero" else None,
        ),
        push_character_snapshot=push,
        events=None,
    )
    host = plugin_host(
        type(world)(world.root, manifest, world.stats, world.currencies, content_override),
        ["effects"],
        server=server,
    )
    server.events = host.events
    server.redis = host.redis
    return host, pushed


def _run(host, verb, session):
    asyncio.run(host.registry.get(verb).handler(session, []))


def test_rest_only_in_safe_rooms_and_only_when_hurt(plugin_host, tmp_path):
    session = StubSession("hero")
    host, _ = _host(plugin_host, tmp_path, session)
    host.redis.stats["hero"] = {"hp": 5, "max_hp": 10}

    host.redis.locations["hero"] = "town:alley"
    _run(host, "rest", session)
    assert "Too dangerous" in session.sent[-1]

    host.redis.locations["hero"] = "town:inn"
    _run(host, "rest", session)
    assert [e["classification"] for e in host.redis.stats["hero"]["effects"]] == ["body.resting"]
    _run(host, "rest", session)
    assert "already resting" in session.sent[-1]

    _run(host, "effects", session)
    assert session.sent[-1].startswith("Active effects:")


def test_fatal_tick_records_death_and_ends_the_session(plugin_host, tmp_path):
    session = StubSession("hero")
    host, pushed = _host(plugin_host, tmp_path, session)
    stats = {"hp": 1, "max_hp": 10}
    apply_effect(
        stats,
        make_effect("hazard.poison", name="poison", kind="dot", magnitude=5, interval=1.0, now=0.0),
    )
    host.redis.stats["hero"] = stats
    host.redis.locations["hero"] = "town:alley"
    job = next(j for j in host.tick_manager._handlers)
    asyncio.run(job(0))
    assert host.redis.stats["hero"]["hp"] == 0
    assert host.redis.stats["hero"]["counters"]["deaths"] == 1
    assert pushed == ["hero"]
    assert session.closed and session.end_reason == "died"
