"""Agent brain plumbing: utterance sanitizer + addressed-line detection."""

from sage_plugin_agents.brain import addressed_line, sanitize_utterance


def test_sanitize_collapses_whitespace_and_quotes():
    assert (
        sanitize_utterance('  "Two lines?\nNot on my  watch."  ') == "Two lines? Not on my watch."
    )


def test_sanitize_strips_command_prefixes():
    assert sanitize_utterance("/say do this") == "say do this"
    assert sanitize_utterance("@teleport somewhere") == "teleport somewhere"


def test_sanitize_caps_length():
    assert len(sanitize_utterance("x" * 500)) == 200


def test_sanitize_neutralizes_inner_quotes():
    assert '"' not in sanitize_utterance('she said "hello" twice')


def test_addressed_line_matches_first_name_case_insensitive():
    lines = [
        'Testa Runn says: "anyone seen the drones?"',
        'Testa Runn says: "hey SELA, any work going?"',
    ]
    assert addressed_line(lines, "Sela Varn", set()) == (
        "Testa Runn",
        "hey SELA, any work going?",
    )


def test_addressed_line_ignores_other_agents_and_self():
    lines = [
        'Sela Varn says: "talking to myself about sela"',
        'Brant Okoro says: "sela, report."',
    ]
    assert addressed_line(lines, "Sela Varn", {"Brant Okoro", "Sela Varn"}) is None


def test_addressed_line_none_when_not_mentioned():
    lines = ['Testa Runn says: "nice weather for a station"']
    assert addressed_line(lines, "Sela Varn", set()) is None


def test_addressed_line_prefers_most_recent():
    lines = [
        'Testa Runn says: "sela, first"',
        'Testa Runn says: "sela, second"',
    ]
    assert addressed_line(lines, "Sela Varn", set())[1] == "sela, second"
