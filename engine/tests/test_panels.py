"""Declarative panels: kinds are closed, `module` is refused, panels are sealed and read own sections."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from sage import lexicon
from sage.network.panels import Panel, PanelRegistry
from sage.network.snapshot import SnapshotContributors
from sage.plugins.manifest import PluginError
from tests import test_plugins
from tests.test_plugins import write_plugin

host_for = test_plugins.host_for  # the plugin-loading fixture, shared

BOARD = """
def setup(api):
    api.snapshot.contribute("board", lambda name, stats: {"rows": [{"label": "posts", "value": 2}]})
    api.ui.panel("posts", "{kind}", "{section}", icon="#")
"""


def test_registry_refuses_reserved_unknown_and_duplicate_kinds():
    panels = PanelRegistry()
    with pytest.raises(ValueError, match="not supported in this engine version"):
        panels.add(Panel(id="x.code", owner="x", kind="module", section="x"))
    with pytest.raises(ValueError, match="unknown panel kind"):
        panels.add(Panel(id="x.pie", owner="x", kind="pie_chart", section="x"))
    panels.add(Panel(id="x.sheet", owner="x", kind="stat_sheet", section="x", icon="*"))
    with pytest.raises(ValueError, match="already declared"):
        panels.add(Panel(id="x.sheet", owner="x", kind="list", section="x"))
    assert panels.specs() == [
        {
            "id": "x.sheet",
            "kind": "stat_sheet",
            "title": "[x.panel.sheet]",
            "icon": "*",
            "section": "x",
        }
    ]
    panels.withdraw("x")
    assert panels.specs() == []


def _load(host_for, tmp_path, kind="key_value", section="board", declared='["board.posts"]'):
    write_plugin(
        tmp_path / "plugins",
        "board",
        BOARD.replace("{kind}", kind).replace("{section}", section),
        touches=f'snapshot = ["board"]\npanels = {declared}\nlexicon_prefix = "board."',
        lexicon="board:\n  panel:\n    posts: 'Notice board'\n",
    )
    host = host_for({"board": "^1"})
    host.server = SimpleNamespace(
        snapshot_contributors=SnapshotContributors(), panels=PanelRegistry()
    )
    host.load()
    return host


def test_plugin_panel_reaches_the_snapshot_specs_with_its_title(host_for, tmp_path):
    host = _load(host_for, tmp_path)
    previous = lexicon.active()
    lexicon.set_active(
        lexicon.build_lexicon(host.world.lexicon_dir, plugin_layers=host.lexicon_layers())
    )
    try:
        assert host.server.panels.specs() == [
            {
                "id": "board.posts",
                "kind": "key_value",
                "title": "Notice board",
                "icon": "#",
                "section": "board",
            }
        ]
    finally:
        lexicon.set_active(previous)
    sections = asyncio.run(host.server.snapshot_contributors.build("pam", {}))
    assert sections["board"] == {"rows": [{"label": "posts", "value": 2}]}
    host.teardown()
    assert host.server.panels.specs() == []


def test_module_panels_are_refused_at_boot(host_for, tmp_path):
    with pytest.raises(PluginError, match="not supported in this engine version"):
        _load(host_for, tmp_path, kind="module")


def test_undeclared_panel_fails_the_seal(host_for, tmp_path):
    with pytest.raises(PluginError, match=r"registered panels \['board.posts'\] not declared"):
        _load(host_for, tmp_path, declared="[]")


def test_panel_must_read_a_section_its_plugin_contributes(host_for, tmp_path):
    with pytest.raises(PluginError, match="does not contribute"):
        _load(host_for, tmp_path, section="progression")
