"""AI slots and their prompt templates (contracts B.6, catalog #10).

A slot is a named narration or generation job (``narrate.room``, ``image.portrait``...). The
engine defines its own slots; plugins declare theirs as ``<plugin>.<name>``. The running world
fills a slot by shipping ``ai/prompts/<slot>.j2``. A slot the world leaves empty is disabled:
rendering it raises ``SlotDisabled`` and the caller falls back to its deterministic path, so a
world without AI (or without one particular job) runs unchanged.
"""

from __future__ import annotations

import logging
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, TemplateNotFound, select_autoescape

from sage.llm.style import AiStyle, load_style

logger = logging.getLogger(__name__)

# The engine's own slots and what each produces.
ENGINE_SLOTS: dict[str, str] = {
    "narrate.room": "prose colour for a room description (look)",
    "forge.room": "a room YAML draft from a staff seed (Nexus forge)",
    "forge.content": "an entity/item/other YAML draft from a staff seed (Nexus forge)",
    "image.area": "an image prompt for a room's area art",
    "image.portrait": "an image prompt for a character portrait",
    "image.scene": "an image prompt for a player's current scene",
}


class SlotDisabled(LookupError):
    """The world ships no template for this slot (or the slot was never declared)."""


class PromptManager:
    """Renders the running world's slot templates; hot reload clears the template cache."""

    def __init__(self, prompt_dir: str | Path, style_path: str | Path | None = None):
        self.prompt_dir = Path(prompt_dir)
        self.style_path = Path(style_path) if style_path is not None else None
        self.style: AiStyle = load_style(self.style_path)
        self._slots: dict[str, str] = dict.fromkeys(ENGINE_SLOTS, "sage")
        self._env = Environment(
            loader=FileSystemLoader(str(self.prompt_dir)), autoescape=select_autoescape()
        )

    def declare(self, slot: str, owner: str) -> None:
        current = self._slots.get(slot)
        if current is not None and current != owner:
            raise ValueError(f"AI slot {slot!r} is already declared by {current!r}")
        self._slots[slot] = owner

    def withdraw(self, owner: str) -> None:
        self._slots = {s: o for s, o in self._slots.items() if o != owner or o == "sage"}

    def slots(self) -> dict[str, dict[str, object]]:
        """Every declared slot with its owner and whether the world fills it."""
        return {
            slot: {"owner": owner, "enabled": self.enabled(slot)}
            for slot, owner in sorted(self._slots.items())
        }

    def enabled(self, slot: str) -> bool:
        return slot in self._slots and (self.prompt_dir / f"{slot}.j2").is_file()

    def render(self, slot: str, **kwargs) -> str:
        """Render a slot's template; raises SlotDisabled when the world does not fill it.

        Templates also see ``style`` (the world's ai/style.yaml) unless the caller passes one.
        """
        if slot not in self._slots:
            raise SlotDisabled(f"AI slot {slot!r} is not declared")
        try:
            template = self._env.get_template(f"{slot}.j2")
        except TemplateNotFound as exc:
            raise SlotDisabled(f"world ships no template for AI slot {slot!r}") from exc
        kwargs.setdefault("style", self.style)
        return template.render(**kwargs)

    def reload(self):
        """Clear the Jinja2 cache and re-read the style file to pick up edits."""
        self._env.cache.clear()
        self.style = load_style(self.style_path)
        logger.info("Prompt template cache cleared.")
