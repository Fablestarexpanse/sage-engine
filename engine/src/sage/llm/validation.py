"""LLM output validator — sanitises generated text before sending to players."""

import logging
import re

logger = logging.getLogger(__name__)


class LLMValidator:
    """
    Ensures LLM output doesn't violate the 'Golden Rule'
    by inventing mechanics or contradicting game state.
    """

    # regex patterns for things the LLM should NEVER say
    FORBIDDEN_PATTERNS = [
        r"(health|hp|mana|energy):?\s*\d+",  # Mentioning specific stats
        r"level\s*\d+",  # Mentioning levels
        r"experience points",  # Mentioning XP
        r"you (gain|lose|find|receive) (a|an|the|\d+)",  # Inventing loot
    ]

    def sanitize(self, text: str) -> str:
        """
        Clean and validate LLM output.
        Returns a cleaned string or a redacted failure message.
        """
        # 1. Strip any preamble (e.g., "Certainly! Here is the description:")
        # We try to find the actual narration block if the LLM was chatty
        text = self._strip_conversational_filler(text)

        # 2. Check for forbidden patterns
        for pattern in self.FORBIDDEN_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                logger.warning(f"LLM validation failed: matched forbidden pattern '{pattern}'")
                return "[The narration becomes garbled by static...]"

        # 3. Final cleanup (whitespace, quotes)
        return text.strip().replace('"', "'")

    def _strip_conversational_filler(self, text: str) -> str:
        """Remove common LLM conversational markers."""
        lines = text.splitlines()
        filtered_lines = []

        for line in lines:
            line_lower = line.lower()
            if line_lower.startswith(("certainly", "here is", "of course", "narrating", "nearing")):
                continue
            if line.strip():
                filtered_lines.append(line)

        return "\n".join(filtered_lines)


validator = LLMValidator()
