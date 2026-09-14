"""Admin routes for agents (mounted at /plugins/agents/admin, tool "agents"): watch, POV,
restart, enable/disable, teleport, give, persona edit, statboard and heatmaps."""

from __future__ import annotations

import os
import tempfile
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from sage.api import PluginAPI

from .feelings import FEELINGS_KEY, MEMORY_KEY, ensure_feelings, mood_word
from .models import AgentPersonaModel

if TYPE_CHECKING:
    from .manager import AgentManager

NON_NEGATIVE_STATS = frozenset({"hp", "max_hp", "xp", "level", "hunger"})


class TeleportBody(BaseModel):
    room_id: str


class GiveBody(BaseModel):
    item_template: str | None = None
    count: int = 1
    stat: str | None = None
    value: int | None = None


class PersonaBody(BaseModel):
    yaml_text: str


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def build_router(api: PluginAPI, manager: AgentManager) -> APIRouter:
    router = APIRouter()

    def _state_or_404(agent_id: str):
        state = manager.agents.get(agent_id) or next(
            (s for s in manager.agents.values() if s.persona.name == agent_id), None
        )
        if state is None:
            raise HTTPException(status_code=404, detail="agent_not_found")
        return state

    def _metrics(stats: dict[str, Any]) -> dict[str, Any]:
        """Play-data metrics for the watch table and detail drawer."""
        counters = stats.get("counters") if isinstance(stats.get("counters"), dict) else {}
        used = {
            k.removeprefix("items_used."): int(v)
            for k, v in counters.items()
            if k.startswith("items_used.")
        }
        return {
            "money": api.wallet.balance(stats),
            "trades": int(counters.get("trades", 0)),
            "kills": int(counters.get("kills", 0)),
            "deaths": int(counters.get("deaths", 0)),
            "goals_completed": int(counters.get("goals_completed", 0)),
            "items_used": int(counters.get("items_used", 0)),
            "most_used_item": max(used, key=used.get) if used else None,
            "levels": api.progression.total_levels(stats),
        }

    @router.get("/heatmaps")
    async def heatmaps():
        """Soak-run aggregates: room presence, kills, deaths, trades, plus per-agent maps."""
        names = ["presence", "kills", "deaths", "trades"]
        names += [f"presence:{pid}" for pid in manager.agents]
        names += [f"kills_by:{s.persona.name}" for s in manager.agents.values()]
        return await api.telemetry.read_heatmaps(names)

    @router.get("/statboard")
    async def statboard():
        """Aggregate play-data board: one row per agent, every counter surfaced."""
        rows = []
        counter_keys: set[str] = set()
        for state in manager.agents.values():
            name = state.persona.name
            stats = await api.characters.stats(name)
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
            memories = stats.get(MEMORY_KEY) if isinstance(stats.get(MEMORY_KEY), list) else []
            flat = {k: int(v) for k, v in counters.items() if isinstance(v, int | float)}
            counter_keys.update(k for k in flat if "." not in k)
            rows.append(
                {
                    "id": state.persona.id,
                    "name": name,
                    "room_id": await api.state.location(name),
                    "hp": stats.get("hp"),
                    "max_hp": stats.get("max_hp"),
                    "mood": mood_word(stats, state.persona),
                    **_metrics(stats),
                    "rooms_visited": len(stats.get("visited_rooms") or []),
                    "top_prey": top_prey,
                    "top_prey_kills": per_prey.get(top_prey, 0) if top_prey else 0,
                    "achievements": sorted(grants.keys()),
                    "memories_count": len(memories),
                    "counters": flat,
                }
            )
        rows.sort(key=lambda r: r["name"])
        # Union of top-level counter keys so the UI grows columns as systems start counting.
        return {"rows": rows, "counter_keys": sorted(counter_keys)}

    @router.get("/agents")
    async def agents_list():
        rows = []
        for state in manager.agents.values():
            name = state.persona.name
            stats = await api.characters.stats(name)
            rows.append(
                {
                    "id": state.persona.id,
                    "name": name,
                    "room_id": await api.state.location(name),
                    "hp": stats.get("hp"),
                    "max_hp": stats.get("max_hp"),
                    "mood": mood_word(stats, state.persona),
                    "goal": state.goal_label,
                    "last_action": state.last_action,
                    "last_action_at": state.last_action_at,
                    "enabled": state.enabled,
                    **_metrics(stats),
                }
            )
        for persona in manager.registry().all():  # on disk but not running
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

    @router.get("/agents/{agent_id}")
    async def agent_detail(agent_id: str):
        state = _state_or_404(agent_id)
        name = state.persona.name
        stats = await api.characters.stats(name)
        ensure_feelings(stats, state.persona)
        return {
            "id": state.persona.id,
            "name": name,
            "room_id": await api.state.location(name),
            # Blocks (progression, feelings, ...) have their own panels; scalars only here.
            "stats": {
                k: v
                for k, v in stats.items()
                if not isinstance(v, dict | list) and k != "progress_log"
            },
            "progress": stats.get("progress_log") or [],
            "feelings": stats.get(FEELINGS_KEY),
            "mood": mood_word(stats, state.persona),
            "inventory": await api.inventory.get(name),
            "goal": state.goal_label,
            "goal_commands": state.goal_commands,
            "metrics": _metrics(stats),
            "skills": api.progression.sheet(stats),
            "equipment": stats.get("equipment") or {},
            "last_action": state.last_action,
            "perceptions": state.session.recent_perceptions(20),
            "persona": state.persona.model_dump(),
            "enabled": state.enabled,
        }

    @router.get("/agents/{agent_id}/pov")
    async def agent_pov(agent_id: str):
        return {"pov": _state_or_404(agent_id).pov[-20:]}

    @router.post("/agents/{agent_id}/restart")
    async def agent_restart(agent_id: str):
        await manager.restart(_state_or_404(agent_id).persona.id)
        return {"status": "ok"}

    @router.post("/agents/{agent_id}/enable")
    async def agent_enable(agent_id: str):
        persona = manager.registry().get(agent_id)  # may be a not-yet-spawned persona
        if persona is None:
            raise HTTPException(status_code=404, detail="agent_not_found")
        if persona.id in manager.agents:
            manager.agents[persona.id].enabled = True
        else:
            await manager.spawn(persona)
        return {"status": "ok"}

    @router.post("/agents/{agent_id}/disable")
    async def agent_disable(agent_id: str):
        _state_or_404(agent_id).enabled = False
        return {"status": "ok"}

    @router.post("/agents/{agent_id}/teleport")
    async def agent_teleport(agent_id: str, body: TeleportBody):
        state = _state_or_404(agent_id)
        if api.content.room(body.room_id) is None:
            raise HTTPException(status_code=400, detail="unknown_room")
        await api.characters.move(state.persona.name, body.room_id)
        return {"status": "ok", "room_id": body.room_id}

    @router.post("/agents/{agent_id}/give")
    async def agent_give(agent_id: str, body: GiveBody):
        name = _state_or_404(agent_id).persona.name
        if body.item_template:
            template = api.content.item_template(body.item_template)
            if template is None:
                raise HTTPException(status_code=400, detail="unknown_item_template")
            inventory = await api.inventory.get(name)
            for _ in range(max(1, body.count)):
                inventory.append(
                    {
                        "id": f"{template.id}_{uuid.uuid4().hex[:8]}",
                        "template": template.id,
                        "name": template.name,
                        "description": template.description,
                        "value": template.value,
                    }
                )
            await api.inventory.set(name, inventory)
            return {"status": "ok", "granted": template.id, "count": max(1, body.count)}
        if body.stat and body.value is not None:
            currencies = {c.key for c in api.world.currencies}
            if body.stat in NON_NEGATIVE_STATS | currencies and body.value < 0:
                raise HTTPException(status_code=400, detail="value_must_be_non_negative")
            stats = await api.characters.stats(name)
            stats[body.stat] = body.value
            await api.characters.save_stats(name, stats)
            return {"status": "ok", "stat": body.stat, "value": body.value}
        raise HTTPException(status_code=400, detail="give_requires_item_or_stat")

    def _persona_path(persona: AgentPersonaModel) -> Path:
        return Path(api.world.content_dir) / "agents" / f"{persona.id}.yaml"

    @router.get("/agents/{agent_id}/persona")
    async def persona_get(agent_id: str):
        persona = manager.registry().get(agent_id)
        if persona is None:
            raise HTTPException(status_code=404, detail="agent_not_found")
        path = _persona_path(persona)
        if not path.exists():
            raise HTTPException(status_code=404, detail="persona_file_missing")
        return {"id": persona.id, "yaml_text": path.read_text(encoding="utf-8")}

    @router.put("/agents/{agent_id}/persona")
    async def persona_put(agent_id: str, body: PersonaBody):
        persona = manager.registry().get(agent_id)
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
        _atomic_write(_persona_path(persona), body.yaml_text)
        # The persona cache reloads on the file change; a running agent picks it up on restart.
        return {
            "status": "ok",
            "applies": "on_restart" if persona.id in manager.agents else "on_spawn",
            "at": time.time(),
        }

    return router
