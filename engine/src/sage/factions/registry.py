"""FactionRegistry — loads content/factions/*.yaml (same pattern as achievements)."""

import logging
from pathlib import Path

import yaml

from sage.factions.models import FactionModel

logger = logging.getLogger(__name__)


class FactionRegistry:
    def __init__(self, factions: list[FactionModel]):
        self._by_id: dict[str, FactionModel] = {}
        # entity template id -> factions that count killing it as service
        self._enemy_of: dict[str, list[FactionModel]] = {}
        for f in factions:
            if f.id in self._by_id:
                logger.warning("Duplicate faction id %r ignored", f.id)
                continue
            self._by_id[f.id] = f
            for tmpl in f.enemies:
                self._enemy_of.setdefault(tmpl, []).append(f)

    def all(self) -> list[FactionModel]:
        return sorted(self._by_id.values(), key=lambda f: f.name)

    def get(self, faction_id: str) -> FactionModel | None:
        return self._by_id.get(faction_id)

    def enemies_of_template(self, template_id: str) -> list[FactionModel]:
        return self._enemy_of.get(template_id, [])


def load_factions(content_dir: Path) -> FactionRegistry:
    factions_dir = Path(content_dir) / "factions"
    results: list[FactionModel] = []
    if factions_dir.is_dir():
        for f in sorted(factions_dir.glob("*.yaml")):
            try:
                with open(f, encoding="utf-8") as fh:
                    data = yaml.safe_load(fh)
                if not isinstance(data, dict):
                    raise ValueError("top-level YAML must be a mapping")
                data.setdefault("id", f.stem)
                results.append(FactionModel(**data))
            except Exception as exc:
                logger.error("Skipping faction %s: %s", f.name, exc)
    return FactionRegistry(results)
