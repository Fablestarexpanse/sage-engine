"""The agents plugin through the host: personas spawn as virtual characters and act."""

import asyncio
from types import SimpleNamespace

from tests.fakes import repo_world


def _server():
    dispatched: list[tuple[str, str]] = []

    async def dispatch(session, line):
        dispatched.append((session.player_id, line))

    def no_database():
        raise RuntimeError("no database in hermetic tests")

    server = SimpleNamespace(
        session_manager=SimpleNamespace(sessions={}, player_to_session={}),
        dispatcher=SimpleNamespace(dispatch=dispatch),
        persistence=SimpleNamespace(flush_hooks=[]),
        db=SimpleNamespace(session_factory=no_database),
        llm_profile=SimpleNamespace(enabled=False),
    )
    return server, dispatched


def test_personas_spawn_attach_claim_names_and_tick(plugin_host):
    server, dispatched = _server()
    host = plugin_host(repo_world(), ["agents"], server=server)
    manager = host.services["agents"][1]
    personas = manager.registry().all()
    assert personas

    asyncio.run(manager.on_tick(0))
    assert set(manager.agents) == {p.id for p in personas if p.enabled}
    spawned = manager.agents[personas[0].id]
    assert server.session_manager.player_to_session[spawned.persona.name]
    assert host.redis.locations[spawned.persona.name] == spawned.persona.spawn_room
    assert host.redis.stats[spawned.persona.name]["is_agent"] is True
    assert len(server.persistence.flush_hooks) == 1
    claimed = {n for _, fn in host.name_claims for n in fn()}
    assert {p.name for p in personas} <= claimed

    asyncio.run(manager.on_tick(1))  # bodies decide; commands go through the dispatcher
    assert all(name in claimed for name, _ in dispatched)
