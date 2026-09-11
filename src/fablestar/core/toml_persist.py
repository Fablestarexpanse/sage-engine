"""Shared helpers for the hand-written TOML persist modules (llm/comfyui settings).

The configs are flat key=value files, so we emit TOML directly rather than pull
in a writer dependency; json.dumps produces valid TOML strings for our values.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


def toml_str(s: str) -> str:
    return json.dumps(s)


def atomic_write_toml(target: Path, lines: list[str]) -> Path:
    """Write joined lines to target atomically (tempfile + os.replace)."""
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".cfg_", suffix=".toml", dir=str(target.parent), text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        os.replace(tmp, target)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return target
