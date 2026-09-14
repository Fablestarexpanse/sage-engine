"""LLMValidator — forbidden-pattern redaction and conversational filler stripping."""

from __future__ import annotations

import unittest

from sage.llm.validation import LLMValidator

REDACTED = "[The narration becomes garbled by static...]"


class TestLLMValidator(unittest.TestCase):
    def setUp(self) -> None:
        self.v = LLMValidator()

    def test_clean_text_passes_through(self) -> None:
        text = "The corridor stretches into darkness, humming faintly."
        self.assertEqual(self.v.sanitize(text), text)

    def test_hp_mention_redacted(self) -> None:
        self.assertEqual(self.v.sanitize("The beast has HP: 12 remaining."), REDACTED)

    def test_level_mention_redacted(self) -> None:
        self.assertEqual(self.v.sanitize("You feel like a level 5 adventurer."), REDACTED)

    def test_xp_mention_redacted(self) -> None:
        self.assertEqual(self.v.sanitize("That grants experience points aplenty."), REDACTED)

    def test_invented_loot_redacted(self) -> None:
        self.assertEqual(self.v.sanitize("You find a gleaming sword on the floor."), REDACTED)

    def test_conversational_filler_stripped(self) -> None:
        text = "Certainly! Here is the description:\nA dim room with rusted walls."
        self.assertEqual(self.v.sanitize(text), "A dim room with rusted walls.")

    def test_double_quotes_become_single(self) -> None:
        self.assertEqual(self.v.sanitize('It whispers "beware".'), "It whispers 'beware'.")

    def test_empty_string_returns_empty(self) -> None:
        self.assertEqual(self.v.sanitize(""), "")

    def test_whitespace_trimmed(self) -> None:
        self.assertEqual(self.v.sanitize("  spooky hall  \n"), "spooky hall")


if __name__ == "__main__":
    unittest.main()
