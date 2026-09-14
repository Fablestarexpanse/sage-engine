"""A world's look in the player client (`ui/theme.yaml`, PHASE1_CONTRACTS D.E).

```yaml
mark: "≈"                 # the mark beside the world's name in headers
accent:
  dark: "#d4a15a"          # accent colour on the dark theme
  light: "#8a5a1c"         # and on the light theme
```

Every field is optional; the client keeps its own palette for anything a world leaves out. An
invalid file logs and reads as empty, so a typo never takes the client down.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ValidationError, field_validator

logger = logging.getLogger(__name__)

HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


class Accent(BaseModel):
    dark: str | None = None
    light: str | None = None

    @field_validator("dark", "light")
    @classmethod
    def _hex(cls, value: str | None) -> str | None:
        if value is not None and not HEX_RE.match(value):
            raise ValueError(f"accent colour {value!r} must be #rrggbb")
        return value


class UiTheme(BaseModel):
    mark: str | None = None
    accent: Accent = Accent()

    @field_validator("mark")
    @classmethod
    def _short(cls, value: str | None) -> str | None:
        if value is not None and not 1 <= len(value) <= 3:
            raise ValueError("mark must be one to three characters")
        return value


def load_ui_theme(root: Path | str) -> dict[str, Any]:
    """The package's ui/theme.yaml as a plain dict with unset fields dropped ({} when absent)."""
    path = Path(root) / "ui" / "theme.yaml"
    if not path.is_file():
        return {}
    try:
        theme = UiTheme(**(yaml.safe_load(path.read_text(encoding="utf-8")) or {}))
    except (ValidationError, TypeError, yaml.YAMLError) as exc:
        logger.error("Ignoring invalid %s: %s", path, exc)
        return {}
    return theme.model_dump(exclude_none=True)
