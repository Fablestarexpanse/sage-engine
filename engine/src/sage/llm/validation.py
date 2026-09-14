"""LLM output validator — sanitises generated narration before it reaches players."""

import logging
import re

from sage.llm.style import DEFAULT_CONTENT_RULES

logger = logging.getLogger(__name__)


class LLMValidator:
    """Rejects narration that breaks the golden rule (stating stats, levels, loot).

    The patterns come from the world's ``ai/style.yaml`` content rules (engine defaults otherwise).
    Rejected narration becomes an empty string: the deterministic text already reached the
    player, so no prose is better than prose that invents mechanics.
    """

    def __init__(self, rules: list[str] | None = None):
        self.rules = list(DEFAULT_CONTENT_RULES if rules is None else rules)

    def sanitize(self, text: str) -> str:
        """Cleaned narration, or "" when it matches a content rule."""
        text = self._strip_conversational_filler(text)
        for pattern in self.rules:
            if re.search(pattern, text, re.IGNORECASE):
                logger.warning("LLM validation failed: matched content rule %r", pattern)
                return ""
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
