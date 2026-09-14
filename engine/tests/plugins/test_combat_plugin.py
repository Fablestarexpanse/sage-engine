"""Combat plugin through the host: damage math, kills, counter-attacks, death, narration, flee."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest import mock

import pytest

from sage.core.events import EntityKilled
from sage.llm.prompts import PromptManager
from sage.world.spawner import EntitySpawnManager
from tests.fakes import StubSession, repo_world

ROOMS = {
    "yard": "id: town:yard\nzone: town\ntype: hub\nexits:\n  north:\n    destination: town:lane\n    description: A gap.\n",
    "lane": "id: town:lane\nzone: town\ntype: hub\n",
    "cellar": "id: town:cellar\nzone: town\ntype: hub\n",
}
ITEMS = {
    "club": "id: club\nname: iron club\nslot: weapon\nattack: 4\n",
    "sling": "id: sling\nname: sling\nslot: weapon\nattack: 3\nammo: pebble\n",
    "pebble": "id: pebble\nname: pebble\n",
}
YARD = "town:yard"
NARRATION = "[narration] {{ narration_facts }}"


def _rat(hp: int = 1, attack: int = 3, **extra) -> dict:
    return {
        "id": "rat_1",
        "name": "Cellar Rat",
        "template": "rat",
        "hp": hp,
        "max_hp": 10,
        "attack": attack,
        "defense": 0,
        "alive": True,
        "loot": [],
        **extra,
    }


class _LLM:
    def __init__(self, prose: str = "", hang: bool = False):
        self.prose, self.hang, self.prompts = prose, hang, []

    async def generate_or_raise(self, prompt: str, max_tokens: int = 250) -> str:
        self.prompts.append(prompt)
        if self.hang:
            await asyncio.sleep(3600)
        return self.prose


def _host(plugin_host, tmp_path, ids=("combat",), llm=None, template=NARRATION):
    content = tmp_path / "content" / "world"
    rooms = content / "zones" / "town" / "rooms"
    rooms.mkdir(parents=True)
    for slug, body in ROOMS.items():
        (rooms / f"{slug}.yaml").write_text(body, encoding="utf-8")
    (content / "items").mkdir()
    for slug, body in ITEMS.items():
        (content / "items" / f"{slug}.yaml").write_text(body, encoding="utf-8")
    world = repo_world()
    manifest = world.manifest.model_copy(deep=True)
    manifest.transition.content_dir = str(tmp_path / "content")
    manifest.params["combat.skills"] = ["brawling"]
    prompt_dir = tmp_path / "ai" / "prompts"
    prompt_dir.mkdir(parents=True)
    if template is not None:
        (prompt_dir / "combat.narration.j2").write_text(template, encoding="utf-8")
    dispatched: list[str] = []

    async def dispatch(session, line):
        dispatched.append(line)

    server = SimpleNamespace(
        prompt_manager=PromptManager(prompt_dir),
        llm_client=llm or _LLM(),
        dispatcher=SimpleNamespace(dispatch=dispatch),
        session_manager=SimpleNamespace(player_to_session={}, get_session_by_player=lambda p: None),
    )
    host = plugin_host(
        type(world)(world.root, manifest, world.stats, world.currencies), list(ids), server=server
    )
    server.events, server.redis, server.content_loader = host.events, host.redis, host.content
    server.spawner = EntitySpawnManager(server)  # type: ignore[arg-type]
    host.redis.locations["hero"] = YARD
    host.redis.stats["hero"] = {"hp": 20, "max_hp": 20}
    return host, dispatched


async def _place(host, state: dict, room: str = YARD) -> None:
    await host.redis.set_entity_state(state["id"], state)
    await host.redis.add_entity_to_room(state["id"], room)


async def _run(host, verb: str, session, *args: str) -> None:
    await host.registry.get(verb).handler(session, list(args))
    for _ in range(5):  # let fire-and-forget narration finish
        await asyncio.sleep(0)


def test_damage_roll_is_attack_plus_d6_minus_defense_at_least_one():
    from sage_plugin_combat.main import roll_damage

    with mock.patch("sage_plugin_combat.main.random.randint", return_value=4):
        assert roll_damage(5, 2) == 7
    with mock.patch("sage_plugin_combat.main.random.randint", return_value=1):
        assert roll_damage(1, 100) == 1


def test_usage_and_unknown_target(plugin_host, tmp_path):
    host, _ = _host(plugin_host, tmp_path)
    session = StubSession("hero")
    asyncio.run(_run(host, "attack", session))
    assert "Attack what?" in session.sent[-1]
    asyncio.run(_run(host, "attack", session, "dragon"))
    assert "no 'dragon' here" in session.sent[-1]


def test_kill_despawns_counts_publishes_and_reports_skill_use(plugin_host, tmp_path):
    host, _ = _host(plugin_host, tmp_path)
    session = StubSession("hero")
    seen: list[EntityKilled] = []

    def on_kill(event: EntityKilled) -> None:
        seen.append(event)
        event.messages.append("The town will remember this.")
        event.stats["counters"]["probe"] = 1

    host.events.subscribe(EntityKilled, on_kill, owner="probe")
    used: list = []

    async def skill_used(player_id, skill, chance):
        used.append((player_id, skill))

    host.resolvers.provide("progression.skill_used", skill_used, owner="probe")

    async def run():
        await _place(host, _rat(hp=1))
        await _run(host, "attack", session, "rat")

    asyncio.run(run())
    assert host.redis.entity_states.get("rat_1") is None
    assert "rat_1" not in host.redis.room_entities.get(YARD, set())
    joined = "\n".join(session.sent)
    assert "You strike Cellar Rat for" in joined and "Cellar Rat is dead." in joined
    assert "The town will remember this." in joined
    assert [(e.killer_id, e.template, e.room_id) for e in seen] == [("hero", "rat", YARD)]
    stats = host.redis.stats["hero"]
    assert stats["counters"]["kills"] == 1 and stats["counters"]["kills.rat"] == 1
    assert stats["counters"]["probe"] == 1  # subscriber writes on the event's stats are saved
    assert used == [("hero", "brawling")]


def test_wounded_target_strikes_back(plugin_host, tmp_path):
    host, _ = _host(plugin_host, tmp_path)
    session = StubSession("hero")

    async def run():
        await _place(host, _rat(hp=100))
        await _run(host, "attack", session, "rat")

    asyncio.run(run())
    assert host.redis.entity_states["rat_1"]["hp"] < 100
    assert host.redis.entity_states["rat_1"]["alive"]
    assert host.redis.stats["hero"]["hp"] < 20
    assert "It strikes back for" in session.sent[0]


def test_dying_counts_the_death_and_ends_the_session(plugin_host, tmp_path):
    host, _ = _host(plugin_host, tmp_path)
    session = StubSession("hero")
    host.redis.stats["hero"] = {"hp": 1, "max_hp": 20}

    async def run():
        await _place(host, _rat(hp=50, attack=30))
        await _run(host, "attack", session, "rat")

    asyncio.run(run())
    assert host.redis.stats["hero"]["hp"] == 0
    assert host.redis.stats["hero"]["counters"]["deaths"] == 1
    assert session.end_reason == "died"


def test_narration_follows_the_outcome_and_never_blocks_it(plugin_host, tmp_path):
    llm = _LLM(prose="The rat squeals once.")
    host, _ = _host(plugin_host, tmp_path, llm=llm)
    session = StubSession("hero")

    async def run():
        await _place(host, _rat(hp=1))
        await _run(host, "attack", session, "rat")

    asyncio.run(run())
    assert session.sent[0].startswith("You strike Cellar Rat")
    assert "The rat squeals once." in session.sent
    assert llm.prompts and llm.prompts[0].startswith("[narration] Player attacks: Cellar Rat")


@pytest.mark.parametrize("broken", ["hang", "raise"])
def test_outcome_stands_when_narration_hangs_or_fails(plugin_host, tmp_path, broken):
    llm = _LLM(hang=True) if broken == "hang" else None
    # A template that calls an undefined function fails at render time.
    template = "{{ missing() }}" if broken == "raise" else NARRATION
    host, _ = _host(plugin_host, tmp_path, llm=llm, template=template)
    session = StubSession("hero")

    async def run():
        await _place(host, _rat(hp=1))
        await asyncio.wait_for(_run(host, "attack", session, "rat"), timeout=1.0)

    asyncio.run(run())
    joined = "\n".join(session.sent)
    assert "It falls." in joined and "Cellar Rat is dead." in joined


def test_worn_gear_adds_attack_and_dry_ammo_weapons_lose_it(plugin_host, tmp_path):
    host, _ = _host(plugin_host, tmp_path, ids=("equipment", "combat"))
    session = StubSession("hero")
    host.redis.inventories["hero"] = [{"id": "p1", "template": "pebble", "name": "pebble"}]
    host.redis.stats["hero"]["equipment"] = {
        "weapon": {"id": "s1", "template": "sling", "name": "sling"}
    }

    async def run():
        with mock.patch("sage_plugin_combat.main.random.randint", return_value=1):
            await _place(host, _rat(hp=100))
            await _run(host, "attack", session, "rat")
            first = 100 - host.redis.entity_states["rat_1"]["hp"]
            await _run(host, "attack", session, "rat")
            second = 100 - first - host.redis.entity_states["rat_1"]["hp"]
        return first, second

    first, second = asyncio.run(run())
    # combat.ratings default for empty stats is 0; the sling adds 3 while it has a pebble.
    assert first - second == 3
    assert host.redis.inventories["hero"] == []
    joined = "\n".join(session.sent)
    assert "That was your last pebble." in joined and "clicks empty" in joined


def test_flee_needs_a_threat_and_an_exit(plugin_host, tmp_path):
    host, dispatched = _host(plugin_host, tmp_path)
    session = StubSession("hero")

    async def run():
        await _run(host, "flee", session)
        assert "nothing here to flee from" in session.sent[-1]
        await _place(host, _rat(), room=YARD)
        with mock.patch("sage_plugin_combat.main.random.random", return_value=0.9):
            await _run(host, "flee", session)
        assert "fail to escape" in session.sent[-1]
        assert host.redis.locations["hero"] == YARD
        with mock.patch("sage_plugin_combat.main.random.random", return_value=0.0):
            await _run(host, "flee", session)
        assert "You flee north!" in session.sent
        assert host.redis.locations["hero"] == "town:lane"
        assert dispatched == ["look"]  # through the server's dispatcher, not a private one
        host.redis.locations["hero"] = "town:cellar"
        await _place(host, _rat() | {"id": "rat_2"}, room="town:cellar")
        await _run(host, "flee", session)
        assert "nowhere to flee" in session.sent[-1]

    asyncio.run(run())


def test_no_narration_work_when_the_world_leaves_the_slot_empty(plugin_host, tmp_path):
    llm = _LLM(prose="should never be asked")
    host, _ = _host(plugin_host, tmp_path, llm=llm, template=None)
    session = StubSession("hero")

    async def run():
        await _place(host, _rat(hp=1))
        await _run(host, "attack", session, "rat")

    asyncio.run(run())
    assert llm.prompts == []
    assert "Cellar Rat is dead." in session.sent
