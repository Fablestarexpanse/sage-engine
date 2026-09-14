"""Agents plugin: computer-controlled characters with a rule-based Body and an LLM Brain."""

from __future__ import annotations

from sage.api import PluginAPI

from .manager import AGENT_TICK_SECONDS, AgentManager
from .routes import build_router


def setup(api: PluginAPI) -> None:
    manager = AgentManager(api)
    api.tick.every(AGENT_TICK_SECONDS, manager.on_tick, name="agents")
    api.persistence.on_flush(manager.flush_all)
    api.characters.claim_names(lambda: [p.name for p in manager.registry().all()])
    api.http.admin_router(build_router(api, manager), tool="agents")
    api.services.provide("agents", manager)
