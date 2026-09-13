"""AgentRegistry — loads content/agents/*.yaml (achievements/factions pattern)."""

import logging
from pathlib import Path

import yaml

from fablestar.agents.models import AgentPersonaModel

logger = logging.getLogger(__name__)


class AgentRegistry:
    def __init__(self, personas: list[AgentPersonaModel]):
        self._by_id: dict[str, AgentPersonaModel] = {}
        self._by_name: dict[str, AgentPersonaModel] = {}
        for p in personas:
            if p.id in self._by_id or p.name in self._by_name:
                logger.warning("Duplicate agent id/name %r/%r ignored", p.id, p.name)
                continue
            self._by_id[p.id] = p
            self._by_name[p.name] = p

    def all(self) -> list[AgentPersonaModel]:
        return sorted(self._by_id.values(), key=lambda p: p.name)

    def get(self, agent_id: str) -> AgentPersonaModel | None:
        return self._by_id.get(agent_id) or self._by_name.get(agent_id)


def load_agents(content_dir: Path) -> AgentRegistry:
    agents_dir = Path(content_dir) / "agents"
    results: list[AgentPersonaModel] = []
    if agents_dir.is_dir():
        for f in sorted(agents_dir.glob("*.yaml")):
            try:
                with open(f, encoding="utf-8") as fh:
                    data = yaml.safe_load(fh)
                if not isinstance(data, dict):
                    raise ValueError("top-level YAML must be a mapping")
                data.setdefault("id", f.stem)
                results.append(AgentPersonaModel(**data))
            except Exception as exc:
                logger.error("Skipping agent persona %s: %s", f.name, exc)
    return AgentRegistry(results)
