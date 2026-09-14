"""AchievementRegistry — loads content/achievements/*.yaml and indexes by counter."""

import logging
from pathlib import Path

import yaml

from sage.achievements.models import AchievementModel

logger = logging.getLogger(__name__)


class AchievementRegistry:
    def __init__(self, achievements: list[AchievementModel]):
        self._by_id: dict[str, AchievementModel] = {}
        self._by_counter: dict[str, list[AchievementModel]] = {}
        for ach in achievements:
            if ach.id in self._by_id:
                logger.warning("Duplicate achievement id %r ignored", ach.id)
                continue
            self._by_id[ach.id] = ach
            for counter in ach.criteria:
                self._by_counter.setdefault(counter, []).append(ach)

    def all(self) -> list[AchievementModel]:
        return sorted(self._by_id.values(), key=lambda a: (a.level_rank, a.name))

    def get(self, achievement_id: str) -> AchievementModel | None:
        return self._by_id.get(achievement_id)

    def watching(self, counter: str) -> list[AchievementModel]:
        """Achievements whose criteria reference this counter."""
        return self._by_counter.get(counter, [])


def load_achievements(content_dir: Path) -> AchievementRegistry:
    """Load every valid achievement file; a bad file is logged and skipped."""
    achievements_dir = Path(content_dir) / "achievements"
    results: list[AchievementModel] = []
    if achievements_dir.is_dir():
        for f in sorted(achievements_dir.glob("*.yaml")):
            try:
                with open(f, encoding="utf-8") as fh:
                    data = yaml.safe_load(fh)
                if not isinstance(data, dict):
                    raise ValueError("top-level YAML must be a mapping")
                data.setdefault("id", f.stem)
                results.append(AchievementModel(**data))
            except Exception as exc:
                logger.error("Skipping achievement %s: %s", f.name, exc)
    return AchievementRegistry(results)
