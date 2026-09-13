"""Cached proficiency registry — the proficiencies package owns its own loading lifecycle."""

import logging
from pathlib import Path

from sage.proficiencies.catalog_loader import load_proficiency_catalog_from_disk
from sage.proficiencies.registry import ProficiencyRegistry

logger = logging.getLogger(__name__)


class ProficiencyRegistryCache:
    """Lazy-loads the Conduit proficiency tree from disk and caches it until invalidated."""

    def __init__(self, content_dir: str | Path = "content"):
        self.content_dir = Path(content_dir)
        self._registry: ProficiencyRegistry | None = None

    def get(self) -> ProficiencyRegistry:
        if self._registry is None:
            doc = load_proficiency_catalog_from_disk(self.content_dir)
            self._registry = ProficiencyRegistry(doc.leaves)
        return self._registry

    def invalidate(self) -> None:
        if self._registry is not None:
            self._registry = None
            logger.info("Proficiency registry cache invalidated")
