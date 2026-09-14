"""Lexicon resolution (contracts B.5) and engine key coverage."""

from __future__ import annotations

import ast
from pathlib import Path

from sage import lexicon
from sage.lexicon import Lexicon, build_lexicon, flatten, load_layer

ENGINE_SRC = Path(__file__).resolve().parents[1] / "src" / "sage"


def test_layers_resolve_in_priority_order(tmp_path):
    (tmp_path / "en.yaml").write_text(
        "who:\n  empty: 'World silence.'\nextra: 'World only'\n", encoding="utf-8"
    )
    lex = build_lexicon(tmp_path, overrides={"extra": "Live override"})
    assert lex.t("who.empty") == "World silence."
    assert lex.source("who.empty") == "world"
    assert lex.t("extra") == "Live override"
    assert lex.source("parser.command_error") == "engine"


def test_missing_key_is_visible_not_silent():
    assert Lexicon([]).t("nope.never") == "[nope.never]"


def test_missing_variable_keeps_placeholder():
    lex = Lexicon([("engine", {"greet": "Hello {name}, you have {count} coins"})])
    assert lex.t("greet", name="Ada") == "Hello Ada, you have {count} coins"


def test_malformed_template_is_returned_unformatted():
    lex = Lexicon([("engine", {"bad": "Broken {brace"})])
    assert lex.t("bad", brace=1) == "Broken {brace"


def test_flatten_and_missing_file(tmp_path):
    assert flatten({"a": {"b": "x", "c": {"d": 1}}, "e": None}) == {"a.b": "x", "a.c.d": "1"}
    assert load_layer(tmp_path / "absent.yaml") == {}


def test_set_active_drives_module_t():
    previous = lexicon.active()
    try:
        lexicon.set_active(Lexicon([("engine", {"k": "v{n}"})]))
        assert lexicon.t("k", n=2) == "v2"
    finally:
        lexicon.set_active(previous)


def _literal_keys_used_by_engine() -> set[str]:
    keys: set[str] = set()
    for path in ENGINE_SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and node.args):
                continue
            func = node.func
            # session.say("k"), lexicon.t("k"), and t("k") after `from sage.lexicon import t`.
            named = (isinstance(func, ast.Attribute) and func.attr in {"say", "t"}) or (
                isinstance(func, ast.Name) and func.id == "t"
            )
            if (
                named
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                keys.add(node.args[0].value)
            # t("a" if cond else "b"): every branch is a key.
            elif named and isinstance(node.args[0], ast.IfExp):
                stack = [node.args[0]]
                while stack:
                    expr = stack.pop()
                    if isinstance(expr, ast.IfExp):
                        stack += [expr.body, expr.orelse]
                    elif isinstance(expr, ast.Constant) and isinstance(expr.value, str):
                        keys.add(expr.value)
    return keys


def test_every_engine_key_has_an_engine_default():
    """No engine code path can render [missing.key] on a world that adds no strings."""
    defaults = load_layer(lexicon.ENGINE_DEFAULTS)
    missing = sorted(_literal_keys_used_by_engine() - defaults.keys())
    assert missing == []
