"""Admin routes for agent NPCs — watch, POV, restart, give, teleport, persona edit."""

import logging
import time
import uuid
from typing import TYPE_CHECKING, Annotated

import yaml
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from sage.admin.admin_security import AdminContext
from sage.admin.route_helpers import require_tool
from sage.agents.feelings import FEELINGS_KEY, ensure_feelings, mood_word
from sage.agents.models import AgentPersonaModel

if TYPE_CHECKING:
    from sage.server import SageServer

logger = logging.getLogger(__name__)


class TeleportBody(BaseModel):
    room_id: str


NON_NEGATIVE_STATS = frozenset({"hp", "max_hp", "xp", "level", "hunger"})


class GiveBody(BaseModel):
    item_template: str | None = None
    count: int = 1
    stat: str | None = None
    value: int | None = None


class PersonaBody(BaseModel):
    yaml_text: str


def build_agents_router(server: "SageServer") -> APIRouter:
    router = APIRouter()

    class _ManagerProxy:
        """Resolve server.agent_manager at request time (test fakes lack it at build)."""

        @property
        def _m(self):
            m = getattr(server, "agent_manager", None)
            if m is None:
                raise HTTPException(status_code=503, detail="agents_unavailable")
            return m

        @property
        def agents(self):
            return self._m.agents

        async def restart(self, agent_id: str):
            await self._m.restart(agent_id)

        async def spawn(self, persona):
            await self._m.spawn(persona)

    manager = _ManagerProxy()

    def _state_or_404(agent_id: str):
        state = manager.agents.get(agent_id)
        if state is None:
            # allow lookup by display name too
            state = next((s for s in manager.agents.values() if s.persona.name == agent_id), None)
        if state is None:
            raise HTTPException(status_code=404, detail="agent_not_found")
        return state

    def _agent_metrics(stats: dict) -> dict:
        """Play-data metrics for the watch table and detail drawer."""
        from sage.world.progression import TOTAL_LEVELS

        counters = stats.get("counters") if isinstance(stats.get("counters"), dict) else {}
        used = {
            k.removeprefix("items_used."): int(v)
            for k, v in counters.items()
            if k.startswith("items_used.")
        }
        most_used = max(used, key=used.get) if used else None
        levels = int(server.resolvers.get(TOTAL_LEVELS)(stats))
        return {
            "digi": server.wallet.balance(stats),
            "trades": int(counters.get("trades", 0)),
            "kills": int(counters.get("kills", 0)),
            "deaths": int(counters.get("deaths", 0)),
            "goals_completed": int(counters.get("goals_completed", 0)),
            "items_used": int(counters.get("items_used", 0)),
            "most_used_item": most_used,
            "levels": levels,
        }

    def _skills_sheet(stats: dict) -> dict:
        from sage.world.progression import SKILL_SHEET

        return server.resolvers.get(SKILL_SHEET)(stats)

    @router.get("/admin/heatmaps")
    async def heatmaps(
        _ctx: Annotated[AdminContext, Depends(require_tool("agents"))],
    ):
        """Soak-run aggregates: room presence, kills, deaths, trades — plus
        per-agent presence maps."""
        from sage.telemetry import read_heatmaps

        names = ["presence", "kills", "deaths", "trades"]
        names += [f"presence:{pid}" for pid in manager.agents]
        names += [f"kills_by:{s.persona.name}" for s in manager.agents.values()]
        return await read_heatmaps(server.redis, names)

    @router.get("/admin/agents-statboard")
    async def agents_statboard(
        _ctx: Annotated[AdminContext, Depends(require_tool("agents"))],
    ):
        """Aggregate play-data board: one row per agent, every counter surfaced."""
        rows = []
        counter_keys: set[str] = set()
        for state in manager.agents.values():
            name = state.persona.name
            stats = await server.redis.get_player_stats(name)
            counters = stats.get("counters") if isinstance(stats.get("counters"), dict) else {}
            per_prey = {
                k.removeprefix("kills."): int(v)
                for k, v in counters.items()
                if k.startswith("kills.")
            }
            top_prey = max(per_prey, key=per_prey.get) if per_prey else None
            grants = (
                stats.get("achievements") if isinstance(stats.get("achievements"), dict) else {}
            )
            memories = (
                stats.get("agent_memories") if isinstance(stats.get("agent_memories"), list) else []
            )
            flat = {k: int(v) for k, v in counters.items() if isinstance(v, int | float)}
            counter_keys.update(k for k in flat if "." not in k)
            rows.append(
                {
                    "id": state.persona.id,
                    "name": name,
                    "room_id": await server.redis.get_player_location(name),
                    "hp": stats.get("hp"),
                    "max_hp": stats.get("max_hp"),
                    "mood": mood_word(stats, state.persona),
                    **_agent_metrics(stats),
                    "rooms_visited": len(stats.get("visited_rooms") or []),
                    "top_prey": top_prey,
                    "top_prey_kills": per_prey.get(top_prey, 0) if top_prey else 0,
                    "achievements": sorted(grants.keys()),
                    "memories_count": len(memories),
                    "counters": flat,
                }
            )
        rows.sort(key=lambda r: r["name"])
        # Union of top-level counter keys so the UI can grow columns as new
        # systems (trades, rentals, ...) start counting.
        return {"rows": rows, "counter_keys": sorted(counter_keys)}

    @router.get("/admin/agents")
    async def agents_list(
        _ctx: Annotated[AdminContext, Depends(require_tool("agents"))],
    ):
        rows = []
        for state in manager.agents.values():
            name = state.persona.name
            stats = await server.redis.get_player_stats(name)
            rows.append(
                {
                    "id": state.persona.id,
                    "name": name,
                    "room_id": await server.redis.get_player_location(name),
                    "hp": stats.get("hp"),
                    "max_hp": stats.get("max_hp"),
                    "mood": mood_word(stats, state.persona),
                    "goal": state.goal_label,
                    "last_action": state.last_action,
                    "last_action_at": state.last_action_at,
                    "enabled": state.enabled,
                    **_agent_metrics(stats),
                }
            )
        # personas on disk but not running (disabled / failed spawn)
        for persona in server.content_loader.get_agent_registry().all():
            if persona.id not in manager.agents:
                rows.append(
                    {
                        "id": persona.id,
                        "name": persona.name,
                        "room_id": None,
                        "hp": None,
                        "max_hp": None,
                        "mood": None,
                        "goal": None,
                        "last_action": "not spawned",
                        "last_action_at": None,
                        "enabled": False,
                    }
                )
        return sorted(rows, key=lambda r: r["name"])

    @router.get("/admin/agents/{agent_id}")
    async def agent_detail(
        agent_id: str,
        _ctx: Annotated[AdminContext, Depends(require_tool("agents"))],
    ):
        state = _state_or_404(agent_id)
        name = state.persona.name
        stats = await server.redis.get_player_stats(name)
        ensure_feelings(stats, state.persona)
        return {
            "id": state.persona.id,
            "name": name,
            "room_id": await server.redis.get_player_location(name),
            # Blocks (progression, feelings, ...) have their own panels; scalars only here.
            "stats": {
                k: v
                for k, v in stats.items()
                if not isinstance(v, dict | list) and k != "progress_log"
            },
            "progress": stats.get("progress_log") or [],
            "feelings": stats.get(FEELINGS_KEY),
            "mood": mood_word(stats, state.persona),
            "inventory": await server.redis.get_player_inventory(name),
            "goal": state.goal_label,
            "goal_commands": state.goal_commands,
            "metrics": _agent_metrics(stats),
            "skills": _skills_sheet(stats),
            "equipment": stats.get("equipment") or {},
            "last_action": state.last_action,
            "perceptions": state.session.recent_perceptions(20),
            "persona": state.persona.model_dump(),
            "enabled": state.enabled,
        }

    @router.get("/admin/agents/{agent_id}/pov")
    async def agent_pov(
        agent_id: str,
        _ctx: Annotated[AdminContext, Depends(require_tool("agents"))],
    ):
        state = _state_or_404(agent_id)
        return {"pov": state.pov[-20:]}

    @router.post("/admin/agents/{agent_id}/restart")
    async def agent_restart(
        agent_id: str,
        _ctx: Annotated[AdminContext, Depends(require_tool("agents"))],
    ):
        state = _state_or_404(agent_id)
        await manager.restart(state.persona.id)
        return {"status": "ok"}

    @router.post("/admin/agents/{agent_id}/enable")
    async def agent_enable(
        agent_id: str,
        _ctx: Annotated[AdminContext, Depends(require_tool("agents"))],
    ):
        # May be a not-yet-spawned persona
        persona = server.content_loader.get_agent_registry().get(agent_id)
        if persona is None:
            raise HTTPException(status_code=404, detail="agent_not_found")
        if persona.id in manager.agents:
            manager.agents[persona.id].enabled = True
        else:
            await manager.spawn(persona)
        return {"status": "ok"}

    @router.post("/admin/agents/{agent_id}/disable")
    async def agent_disable(
        agent_id: str,
        _ctx: Annotated[AdminContext, Depends(require_tool("agents"))],
    ):
        state = _state_or_404(agent_id)
        state.enabled = False
        return {"status": "ok"}

    @router.post("/admin/agents/{agent_id}/teleport")
    async def agent_teleport(
        agent_id: str,
        body: TeleportBody,
        _ctx: Annotated[AdminContext, Depends(require_tool("agents"))],
    ):
        state = _state_or_404(agent_id)
        if server.content_loader.get_room(body.room_id) is None:
            raise HTTPException(status_code=400, detail="unknown_room")
        await server.redis.set_player_location(state.persona.name, body.room_id)
        return {"status": "ok", "room_id": body.room_id}

    @router.post("/admin/agents/{agent_id}/give")
    async def agent_give(
        agent_id: str,
        body: GiveBody,
        _ctx: Annotated[AdminContext, Depends(require_tool("agents"))],
    ):
        state = _state_or_404(agent_id)
        name = state.persona.name
        if body.item_template:
            template = server.content_loader.get_item_template(body.item_template)
            if template is None:
                raise HTTPException(status_code=400, detail="unknown_item_template")
            inv = await server.redis.get_player_inventory(name)
            for _ in range(max(1, body.count)):
                inv.append(
                    {
                        "id": f"{template.id}_{uuid.uuid4().hex[:8]}",
                        "template": template.id,
                        "name": template.name,
                        "description": template.description,
                        "value": template.value,
                    }
                )
            await server.redis.set_player_inventory(name, inv)
            return {"status": "ok", "granted": template.id, "count": max(1, body.count)}
        if body.stat and body.value is not None:
            currencies = {c.key for c in server.world.currencies}
            if body.stat in NON_NEGATIVE_STATS | currencies and body.value < 0:
                raise HTTPException(status_code=400, detail="value_must_be_non_negative")
            stats = await server.redis.get_player_stats(name)
            stats[body.stat] = body.value
            await server.redis.set_player_stats(name, stats)
            return {"status": "ok", "stat": body.stat, "value": body.value}
        raise HTTPException(status_code=400, detail="give_requires_item_or_stat")

    @router.get("/admin/agents/{agent_id}/persona")
    async def persona_get(
        agent_id: str,
        _ctx: Annotated[AdminContext, Depends(require_tool("agents"))],
    ):
        persona = server.content_loader.get_agent_registry().get(agent_id)
        if persona is None:
            raise HTTPException(status_code=404, detail="agent_not_found")
        path = server.world.content_dir / "agents" / f"{persona.id}.yaml"
        if not path.exists():
            raise HTTPException(status_code=404, detail="persona_file_missing")
        return {"id": persona.id, "yaml_text": path.read_text(encoding="utf-8")}

    @router.put("/admin/agents/{agent_id}/persona")
    async def persona_put(
        agent_id: str,
        body: PersonaBody,
        _ctx: Annotated[AdminContext, Depends(require_tool("agents"))],
    ):
        persona = server.content_loader.get_agent_registry().get(agent_id)
        if persona is None:
            raise HTTPException(status_code=404, detail="agent_not_found")
        try:
            data = yaml.safe_load(body.yaml_text)
            if not isinstance(data, dict):
                raise ValueError("top-level YAML must be a mapping")
            data.setdefault("id", persona.id)
            AgentPersonaModel(**data)  # validate before touching disk
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"invalid_persona: {exc}") from exc

        from sage.admin.content_browser import _atomic_write_text

        _atomic_write_text(
            server.world.content_dir / "agents" / f"{persona.id}.yaml", body.yaml_text
        )
        server.content_loader._cache.pop("agents:registry", None)
        # Running agent picks the edit up on restart; report which applies.
        running = persona.id in manager.agents
        return {
            "status": "ok",
            "applies": "on_restart" if running else "on_spawn",
            "at": time.time(),
        }

    return router
