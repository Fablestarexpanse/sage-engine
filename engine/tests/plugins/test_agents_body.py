"""Agent Body: decision priorities, routing, persona loading, session plumbing."""

import asyncio
import random

from sage_plugin_agents.body import BodyContext, decide, hostiles_in, route_step
from sage_plugin_agents.registry import load_agents
from sage_plugin_agents.session import AgentSession


def _ctx(**overrides) -> BodyContext:
    base = {
        "hp": 60,
        "max_hp": 60,
        "room_type": "corridor",
        "exits": ["north", "south"],
        "hostiles": [],
        "consumables": [],
        "resting": False,
        "goal_commands": [],
        "next_routine_direction": None,
        "wander_ready": True,
    }
    base.update(overrides)
    return BodyContext(**base)


def test_flee_beats_fight_when_critical():
    reason, cmd = decide(_ctx(hp=10, hostiles=["drone"]), random.Random(1))
    assert reason == "flee" and cmd in ("north", "south")


def test_fight_when_healthy_and_hostile_present():
    reason, cmd = decide(_ctx(hostiles=["feral scrap drone"]), random.Random(1))
    assert (reason, cmd) == ("fight", "attack feral scrap drone")


def test_eat_when_hurt_with_food():
    reason, cmd = decide(_ctx(hp=20, consumables=["sealed ration pack"]))
    assert (reason, cmd) == ("eat", "use sealed ration pack")


def test_rest_in_safe_room_when_hurt():
    reason, cmd = decide(_ctx(hp=40, room_type="safe"))
    assert (reason, cmd) == ("rest", "rest")


def test_rest_skipped_when_already_resting():
    reason, _ = decide(_ctx(hp=40, room_type="safe", resting=True))
    assert reason in ("idle", "wander")


def test_goal_before_wander():
    reason, cmd = decide(_ctx(goal_commands=["north"], next_routine_direction="south"))
    assert (reason, cmd) == ("goal", "north")


def test_wander_respects_cooldown():
    reason, cmd = decide(_ctx(next_routine_direction="north", wander_ready=False))
    assert (reason, cmd) == ("idle", None)


def test_route_step_bfs_first_move():
    exits = {
        "z:a": {"north": "z:b"},
        "z:b": {"south": "z:a", "east": "z:c"},
        "z:c": {"west": "z:b"},
    }
    assert route_step("z:a", "z:c", exits) == "north"
    assert route_step("z:a", "z:a", exits) is None
    assert route_step("z:a", "z:missing", exits) is None


def test_hostiles_in_uses_template_tags():
    ents = [
        {"template": "scrap_drone", "name": "feral scrap drone", "alive": True},
        {"template": "scrap_drone", "name": "dead drone", "alive": False},
        {"template": "cat", "name": "station cat", "alive": True},
    ]
    tags = {"scrap_drone": {"hostile"}, "cat": {"cute"}}
    assert hostiles_in(ents, tags.get) == ["feral scrap drone"]


def test_agent_session_collects_perception():
    s = AgentSession("pam", "Puppet Pam")
    heard = "You move north."
    asyncio.run(s.send(heard))
    asyncio.run(s.send_prompt())
    assert s.recent_perceptions() == ["You move north."]
    assert s.player_id == "Puppet Pam"
    assert s.protocol.is_connected


def test_world_personas_all_load(tmp_path):
    from tests.fakes import repo_world

    agents_dir = repo_world().content_dir / "agents"
    files = sorted(agents_dir.glob("*.yaml"))
    reg = load_agents(agents_dir)
    assert files and len(reg.all()) == len(files)  # nothing skipped as invalid
    for persona in reg.all():
        assert ":" in persona.spawn_room and isinstance(persona.gear, dict)
        assert reg.get(persona.name) is persona
