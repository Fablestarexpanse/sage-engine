"""Plugin migration helpers that need no database (contracts D.D)."""

from __future__ import annotations

import os
from pathlib import Path

from sage.plugins.migrations import (
    ENGINE_DIR,
    alembic_config,
    is_core_object,
    plugin_branch,
    plugin_migration_dir,
)
from sage.plugins.uninstall import dependents, remove_from_world_manifest


class _Rec:
    def __init__(self, pid, depends):
        self.id = pid
        self.manifest = type("M", (), {"depends": depends})()


class _Dep:
    def __init__(self, optional=False):
        self.optional = optional


def test_alembic_config_includes_plugin_version_dirs(tmp_path):
    with_migrations = tmp_path / "ledger"
    (with_migrations / "migrations" / "versions").mkdir(parents=True)
    without = tmp_path / "plain"
    without.mkdir()
    cfg = alembic_config([with_migrations, without])
    locations = cfg.get_main_option("version_locations").split(os.pathsep)
    assert locations == [
        str(ENGINE_DIR / "alembic" / "versions"),
        str(with_migrations / "migrations" / "versions"),
    ]
    assert plugin_migration_dir(without) is None
    assert plugin_branch("ledger") == "plg_ledger"


def test_core_autogenerate_ignores_plugin_tables():
    assert is_core_object(None, "characters", "table", True, None)
    assert not is_core_object(None, "plg_ledger_entries", "table", True, None)
    assert is_core_object(None, "plg_ledger_entries_idx", "index", True, None)


def test_required_dependents_block_uninstall():
    records = [
        _Rec("base", {}),
        _Rec("needs_base", {"base": _Dep()}),
        _Rec("likes_base", {"base": _Dep(optional=True)}),
    ]
    assert dependents(records, "base") == ["needs_base"]
    assert dependents(records, "needs_base") == []


def test_remove_from_world_manifest_keeps_everything_else(tmp_path):
    toml = tmp_path / "world.toml"
    toml.write_text(
        '[world]\nid = "demo"\n\n[plugins]\n# progression\nlevels = "^1"\nledger = "^1"\n\n'
        '[params]\n"ledger.fee" = 2\n',
        encoding="utf-8",
    )
    assert remove_from_world_manifest(toml, "ledger") is True
    assert toml.read_text(encoding="utf-8") == (
        '[world]\nid = "demo"\n\n[plugins]\n# progression\nlevels = "^1"\n\n'
        '[params]\n"ledger.fee" = 2\n'
    )
    assert remove_from_world_manifest(toml, "ledger") is False


def test_core_chain_is_labelled():
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(alembic_config())
    [head] = script.get_heads()
    assert "sage_core" in script.get_revision(head).branch_labels
    assert Path(script.get_revision(head).path).parent == ENGINE_DIR / "alembic" / "versions"
