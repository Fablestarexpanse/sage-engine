"""The SAGE invariant ratchet scanner (scripts/sage_invariants.py)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "sage_invariants.py"


@pytest.fixture(scope="module")
def inv():
    spec = importlib.util.spec_from_file_location("sage_invariants", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["sage_invariants"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def denylist(inv):
    return inv.Denylist(
        insensitive=["conduit", "digi", "glyph", "glyphstream", "pixels"],
        sensitive=["Resolve", "Presence", "Pixel"],
        acronyms=["FRT", "RFX"],
    )


def _hits(inv, text, denylist) -> int:
    return sum(inv.find_terms(text, denylist).values())


def test_snake_and_camel_boundaries(inv, denylist):
    assert _hits(inv, "character.digi_balance", denylist) == 1
    assert _hits(inv, "CONDUIT_KEY = 1", denylist) == 1
    assert _hits(inv, "<ConduitGlassStrip />", denylist) == 1
    assert _hits(inv, "stats.conduit.attrs", denylist) == 1
    assert _hits(inv, "const mudConduit = 1", denylist) == 1
    assert _hits(inv, "conduction digital", denylist) == 0


def test_plural_and_compound_terms(inv, denylist):
    assert _hits(inv, "your Glyphs", denylist) == 1
    counts = inv.find_terms("the Glyphstream flows", denylist)
    assert counts == {"glyphstream": 1}


def test_overlapping_terms_count_once(inv, denylist):
    assert _hits(inv, "spend Pixels", denylist) == 1


def test_sensitive_terms_ignore_code_words(inv, denylist):
    assert _hits(inv, "resolve_project_root()", denylist) == 0
    assert _hits(inv, "Promise.resolve(x)", denylist) == 0
    assert _hits(inv, "presence_count", denylist) == 0
    assert _hits(inv, 'label = "Resolve"', denylist) == 1
    assert _hits(inv, "{ RSV: 'Resolve', PRS: `Presence` }", denylist) == 2
    assert _hits(inv, "Resolved the issue", denylist) == 0


def test_sensitive_terms_only_count_inside_string_literals(inv, denylist):
    assert _hits(inv, '    """Resolve a path from config."""', denylist) == 0
    assert _hits(inv, "# Presence + log WebSockets", denylist) == 0
    assert _hits(inv, "function adminPresenceWsUrl() {}", denylist) == 0
    assert _hits(inv, 'x = "Presence of mind"', denylist) == 1


def test_acronyms_standalone(inv, denylist):
    assert _hits(inv, '"FRT/RFX"', denylist) == 2
    assert _hits(inv, "FRTX frt", denylist) == 0


def test_player_literal_detection(inv):
    source = """
async def handler(session, msg, a, b, ws, p):
    await session.send("x")
    await session.send(f"{a}")
    await session.send("a" + b)
    await session.send("hp %d" % a)
    await session.send("hi {}".format(a))
    await session.end("reason", "bye")
    await manager.broadcast("hello")
    await session.send(msg)
    await ws.send(json.dumps(p))
    await session.end("reason")
"""
    assert inv.count_player_literals(source) == 7


def test_player_literal_detection_survives_syntax_errors(inv):
    assert inv.count_player_literals("def broken(:\n") == 0


def test_compare_ratchet(inv):
    baseline = {"denylist": {"a.py": 3}, "player_literals": {"b.py": 2}}
    assert inv.compare(baseline, {"denylist": {"a.py": 2}, "player_literals": {}}) == []
    worse = inv.compare(baseline, {"denylist": {"a.py": 4}, "player_literals": {"b.py": 2}})
    assert len(worse) == 1 and "a.py" in worse[0]
    new = inv.compare(baseline, {"denylist": {"a.py": 3, "c.py": 1}, "player_literals": {}})
    assert len(new) == 1 and "c.py" in new[0]


def test_world_terms_from_packages(inv, tmp_path):
    world = tmp_path / "worlds" / "demo"
    world.mkdir(parents=True)
    (world / "stats.yaml").write_text(
        "attributes:\n  - key: might\n    label: stat.might.name\n", encoding="utf-8"
    )
    (world / "currencies.yaml").write_text("- key: silver\n  starting: 5\n", encoding="utf-8")
    assert inv.world_terms(tmp_path) == ["might", "silver"]
