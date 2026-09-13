"""ContentLoader — lazy, cached YAML loader for world content (rooms, entities, items)."""

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeVar

import yaml
from pydantic import BaseModel

from fablestar.proficiencies.registry import ProficiencyRegistry
from fablestar.proficiencies.registry_cache import ProficiencyRegistryCache
from fablestar.world.models import EntityTemplate, ItemTemplate, RoomModel

if TYPE_CHECKING:
    from fablestar.achievements.registry import AchievementRegistry
    from fablestar.agents.registry import AgentRegistry
    from fablestar.factions.registry import FactionRegistry

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class ContentLoader:
    """
    Loads and caches YAML content with validation.
    Supports invalidating cache for hot-reloads.
    """

    def __init__(self, content_dir: str = "content"):
        self.content_dir = Path(content_dir)
        self._cache: dict[str, Any] = {}
        self._proficiency_cache = ProficiencyRegistryCache(self.content_dir)

    def _get_cache_key(self, content_type: str, content_id: str) -> str:
        return f"{content_type}:{content_id}"

    def load_yaml(self, file_path: Path, model_class: type[T]) -> T:
        """Load and validate a single YAML file."""
        with open(file_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return model_class(**data)

    def get_room(self, room_id: str) -> RoomModel | None:
        """Get a room from cache or load it from disk."""
        cache_key = self._get_cache_key("room", room_id)
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Room IDs are formatted as "zone_id:room_id"
        # File path: content/world/zones/{zone_id}/rooms/{room_id}.yaml
        try:
            zone_id, room_filename = room_id.split(":")
            room_path = (
                self.content_dir / "world" / "zones" / zone_id / "rooms" / f"{room_filename}.yaml"
            )

            if not room_path.exists():
                logger.error(f"Room file not found: {room_path}")
                return None

            room = self.load_yaml(room_path, RoomModel)
            self._cache[cache_key] = room
            return room
        except ValueError:
            logger.error(f"Invalid room ID format: {room_id}")
            return None
        except Exception as e:
            logger.error(f"Error loading room {room_id}: {e}")
            return None

    def get_entity_template(self, entity_id: str) -> EntityTemplate | None:
        """Load and cache an entity template from content/world/entities/{id}.yaml."""
        cache_key = self._get_cache_key("entity", entity_id)
        if cache_key in self._cache:
            return self._cache[cache_key]
        path = self.content_dir / "world" / "entities" / f"{entity_id}.yaml"
        if not path.exists():
            logger.error(f"Entity template not found: {path}")
            return None
        try:
            template = self.load_yaml(path, EntityTemplate)
            self._cache[cache_key] = template
            return template
        except Exception as e:
            logger.error(f"Error loading entity template {entity_id}: {e}")
            return None

    def get_item_template(self, item_id: str) -> ItemTemplate | None:
        """Load and cache an item template from content/world/items/{id}.yaml."""
        cache_key = self._get_cache_key("item", item_id)
        if cache_key in self._cache:
            return self._cache[cache_key]
        path = self.content_dir / "world" / "items" / f"{item_id}.yaml"
        if not path.exists():
            logger.error(f"Item template not found: {path}")
            return None
        try:
            template = self.load_yaml(path, ItemTemplate)
            self._cache[cache_key] = template
            return template
        except Exception as e:
            logger.error(f"Error loading item template {item_id}: {e}")
            return None

    def list_item_template_ids(self) -> list[str]:
        """All item template ids on disk (file stems under content/world/items)."""
        items_dir = self.content_dir / "world" / "items"
        if not items_dir.is_dir():
            return []
        return sorted(p.stem for p in items_dir.glob("*.yaml"))

    def list_entity_templates(self) -> list[EntityTemplate]:
        """Return all entity templates found on disk."""
        entities_dir = self.content_dir / "world" / "entities"
        if not entities_dir.is_dir():
            return []
        results = []
        for f in sorted(entities_dir.glob("*.yaml")):
            tmpl = self.get_entity_template(f.stem)
            if tmpl:
                results.append(tmpl)
        return results

    def list_item_templates(self) -> list[ItemTemplate]:
        """Return all item templates found on disk."""
        items_dir = self.content_dir / "world" / "items"
        if not items_dir.is_dir():
            return []
        results = []
        for f in sorted(items_dir.glob("*.yaml")):
            tmpl = self.get_item_template(f.stem)
            if tmpl:
                results.append(tmpl)
        return results

    def get_proficiency_registry(self) -> ProficiencyRegistry:
        """Delegate to the proficiencies package's own registry cache."""
        return self._proficiency_cache.get()

    def get_achievement_registry(self) -> "AchievementRegistry":
        """Load and cache the achievement registry from content/achievements/."""
        cache_key = "achievements:registry"
        if cache_key in self._cache:
            return self._cache[cache_key]
        from fablestar.achievements.registry import load_achievements

        registry = load_achievements(self.content_dir)
        self._cache[cache_key] = registry
        return registry

    def get_agent_registry(self) -> "AgentRegistry":
        """Load and cache agent personas from content/agents/."""
        cache_key = "agents:registry"
        if cache_key in self._cache:
            return self._cache[cache_key]
        from fablestar.agents.registry import load_agents

        registry = load_agents(self.content_dir)
        self._cache[cache_key] = registry
        return registry

    def get_faction_registry(self) -> "FactionRegistry":
        """Load and cache the faction registry from content/factions/."""
        cache_key = "factions:registry"
        if cache_key in self._cache:
            return self._cache[cache_key]
        from fablestar.factions.registry import load_factions

        registry = load_factions(self.content_dir)
        self._cache[cache_key] = registry
        return registry

    def invalidate(self, file_path: Path):
        """Invalidate cache entries associated with a changed file."""
        # Simple implementation: clear all or try to match path
        # In a more advanced version, we would maps paths to cache keys
        logger.info(f"Invalidating cache for {file_path}")

        # For now, we'll just clear the specific type if we can determine it
        if "proficiencies" in file_path.parts:
            self._proficiency_cache.invalidate()
        elif "rooms" in file_path.parts:
            room_id = f"{file_path.parent.parent.name}:{file_path.stem}"
            cache_key = self._get_cache_key("room", room_id)
            if cache_key in self._cache:
                del self._cache[cache_key]
                logger.info(f"Evicted {cache_key} from cache")
        else:
            # If unsure, clear everything to be safe
            self.clear_cache()

    def clear_cache(self):
        """Force clear the entire content cache."""
        self._cache.clear()
        self._proficiency_cache.invalidate()
        logger.info("Content cache cleared.")
