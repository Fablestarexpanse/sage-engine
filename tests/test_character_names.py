"""Character name rules: shape, reserved words, command verbs, agent names."""

from __future__ import annotations

import fablestar.commands.info  # noqa: F401 — registers look/examine
from fablestar.services.player_service import PlayerService, reserved_name_reason

AGENTS = {"sela varn", "old pell"}


def _shape_ok(name: str) -> bool:
    return PlayerService._validate_create_character_inputs(name, "", "")[0] is None


def test_shape_rules():
    assert _shape_ok("Qa Tester")
    assert _shape_ok("Q7")
    assert not _shape_ok("Q")
    assert not _shape_ok("Qa-")
    assert not _shape_ok("-Qa")
    assert not _shape_ok("Qa  Tester")
    assert not _shape_ok("A" * 51)


def test_agent_names_blocked_case_insensitively():
    assert reserved_name_reason("Sela Varn", AGENTS) == "character_name_taken"
    assert reserved_name_reason("sela varn", AGENTS) == "character_name_taken"
    assert reserved_name_reason("SELA   VARN", AGENTS) == "character_name_taken"


def test_reserved_words_and_commands():
    for name in ("admin", "North", "look", "Examine", "System"):
        assert reserved_name_reason(name, AGENTS) == "character_name_reserved", name
    assert reserved_name_reason("Admin Bob", AGENTS) == "character_name_reserved"


def test_ordinary_names_pass():
    for name in ("Qa Tester", "Testa Runn", "Upton Downs", "Menarly"):
        assert reserved_name_reason(name, AGENTS) is None, name
