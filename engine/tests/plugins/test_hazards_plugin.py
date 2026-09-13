"""Hazards plugin: severity-scaled DoTs, resist through progression, and entering a room."""

import asyncio
import random

from sage_plugin_hazards.main import HazardModel, apply_hazards

from sage.core.events import RoomEntered
from sage.world.progression import SKILL_LEVEL, SKILL_USED
from tests.fakes import repo_world

T0 = 1_000_000.0
VENT = HazardModel(
    id="vent", type="radiation", severity=3, description="Radiation prickles across your skin."
)


def _api(host):
    return next(r.api for r in host.loaded if r.id == "hazards")


def test_hazard_applies_dot_scaled_by_severity(plugin_host):
    api = _api(plugin_host(repo_world(), ["hazards"]))
    state = {"hp": 20}
    msgs = apply_hazards(api, state, [VENT], resist=0.0, rng=random.Random(1), now=T0)
    (eff,) = api.effects.find(state, "hazard.radiation")
    assert eff["magnitude"] == 3
    assert eff["expires_at"] == T0 + 30.0  # 6 * (2 + 3)
    assert msgs == ["Radiation prickles across your skin. (radiation takes hold)"]


def test_resisted_hazard_applies_nothing(plugin_host):
    api = _api(plugin_host(repo_world(), ["hazards"]))
    state = {"hp": 20}
    msgs = apply_hazards(api, state, [VENT], resist=0.75, rng=random.Random(1), now=T0)
    assert api.effects.find(state, "hazard.radiation") == []
    assert msgs == ["You brace against the radiation and shrug it off."]


ROOM = """id: town:vent
zone: town
type: danger
hazards:
  - {id: vent, type: radiation, severity: 1, description: The air hums.}
"""


def test_entering_a_hazard_room_applies_effects_and_reports_skill_use(plugin_host, tmp_path):
    rooms = tmp_path / "content" / "world" / "zones" / "town" / "rooms"
    rooms.mkdir(parents=True)
    (rooms / "vent.yaml").write_text(ROOM, encoding="utf-8")
    (rooms / "lane.yaml").write_text("id: town:lane\nzone: town\ntype: hub\n", encoding="utf-8")
    world = repo_world()
    manifest = world.manifest.model_copy(deep=True)
    manifest.transition.content_dir = str(tmp_path / "content")
    manifest.params["hazards.resist_skill"] = "toughness"
    host = plugin_host(
        type(world)(world.root, manifest, world.stats, world.currencies), ["hazards"]
    )
    used: list[str] = []

    async def skill_used(player_id, skill, chance):
        used.append(skill)

    host.resolvers.provide(SKILL_USED, skill_used, owner="test")
    host.resolvers.provide(SKILL_LEVEL, lambda stats, skill: 0, owner="test")
    host.redis.stats["hero"] = {"hp": 9}

    quiet = RoomEntered(player_id="hero", room_id="town:lane", from_room_id=None)
    asyncio.run(host.events.publish(quiet))
    assert quiet.messages == [] and used == []

    entered = RoomEntered(player_id="hero", room_id="town:vent", from_room_id="town:lane")
    asyncio.run(host.events.publish(entered))
    assert entered.messages == ["The air hums. (radiation takes hold)"]
    assert [e["classification"] for e in host.redis.stats["hero"]["effects"]] == [
        "hazard.radiation"
    ]
    assert host.redis.stats["hero"]["hp"] == 9
    assert used == ["toughness"]
