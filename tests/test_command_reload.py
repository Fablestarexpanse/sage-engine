"""Hot-reloading a command module must drop commands and aliases the new source no longer defines."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

from fablestar.commands.registry import registry

MODULE = "zz_reload_probe_cmds"

V1 = '''
from fablestar.commands.registry import command

@command("zzprobe", aliases=["zzp1", "zzp2"])
async def zzprobe(session, args):
    """v1"""

@command("zzgone")
async def zzgone(session, args):
    """removed in v2"""
'''

V2 = '''
from fablestar.commands.registry import command

@command("zzprobe", aliases=["zzp1"])
async def zzprobe(session, args):
    """v2 keeps one alias and drops the zzgone command entirely"""
'''

BROKEN = "this is not python ::::\n"


@pytest.fixture
def probe_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setattr(sys, "dont_write_bytecode", True)
    commands = dict(registry._commands)
    aliases = dict(registry._aliases)
    modules = dict(registry._modules)
    path = tmp_path / f"{MODULE}.py"
    path.write_text(V1, encoding="utf-8")
    yield path
    registry._commands.clear()
    registry._commands.update(commands)
    registry._aliases.clear()
    registry._aliases.update(aliases)
    registry._modules.clear()
    registry._modules.update(modules)
    sys.modules.pop(MODULE, None)


def _rewrite(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    importlib.invalidate_caches()


def test_reload_drops_removed_commands_and_aliases(probe_module: Path) -> None:
    registry.load_module_strict(MODULE)
    assert registry.get("zzp2") is not None
    assert registry.get("zzgone") is not None

    _rewrite(probe_module, V2)
    registry.reload_module(MODULE)

    assert registry.get("zzprobe").handler.__doc__.startswith("v2")
    assert registry.get("zzp1") is not None
    assert registry.get("zzp2") is None
    assert registry.get("zzgone") is None


def test_failed_reload_keeps_previous_commands(probe_module: Path) -> None:
    registry.load_module_strict(MODULE)

    _rewrite(probe_module, BROKEN)
    registry.reload_module(MODULE)  # lenient: logs and keeps running

    assert registry.get("zzprobe") is not None
    assert registry.get("zzp2") is not None
    assert registry.get("zzgone") is not None
