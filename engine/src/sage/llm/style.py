"""A world's AI style (``ai/style.yaml``, contracts B.6): the voice every slot template shares.

Templates read it as ``{{ style.tone }}`` and ``{{ style.image.style }}``; the engine uses the
system prompt for narration requests and the content rules to reject prose that states game
mechanics. Every field is optional: a world without the file gets neutral defaults.

```yaml
tone: "dark, ancient sci-fi; technology is indistinguishable from ritual"
system_prompt: "You are a master storyteller for a dark sci-fi text game."
image:
  style: "sci-fi, atmospheric"
  negative: "text, watermark"
content_rules:            # regexes narration must not match (replaces the defaults)
  - 'level\\s*\\d+'
```
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator

logger = logging.getLogger(__name__)

# The golden rule in regex form: narration describes, it never states numbers or rewards.
DEFAULT_CONTENT_RULES = [
    r"(health|hp|mana|energy):?\s*\d+",
    r"level\s*\d+",
    r"experience points",
    r"you (gain|lose|find|receive) (a|an|the|\d+)",
]


class ImageStyle(BaseModel):
    style: str = ""
    negative: str = ""


class AiStyle(BaseModel):
    tone: str = ""
    system_prompt: str = "You narrate for a text game. Describe only what the facts give you."
    image: ImageStyle = Field(default_factory=ImageStyle)
    content_rules: list[str] | None = None

    @field_validator("content_rules")
    @classmethod
    def _rules_compile(cls, value: list[str] | None) -> list[str] | None:
        for rule in value or []:
            re.compile(rule)
        return value

    def rules(self) -> list[str]:
        return list(DEFAULT_CONTENT_RULES if self.content_rules is None else self.content_rules)


def load_style(path: Path | None) -> AiStyle:
    """The style file at path, or defaults when it is missing. An invalid file logs and falls back."""
    if path is None or not Path(path).is_file():
        return AiStyle()
    try:
        return AiStyle(**(yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}))
    except (ValidationError, yaml.YAMLError, re.error, TypeError) as exc:
        logger.error("AI style %s is invalid, using defaults: %s", path, exc)
        return AiStyle()
