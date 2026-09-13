"""
AgentBrain — the LLM half. Voice replies (M3); intent goals (M4).

Own LLMClient on config.agents_llm (separate endpoint + its own circuit
breaker), so a dead brain endpoint costs one fast-fail and the Body keeps
living on rules. All output is sanitized and re-enters the world only as a
plain `say` command through the dispatcher.
"""

import logging
import re
import time
from typing import TYPE_CHECKING, Any

from fablestar.llm.client import LLMClient, LLMGenerationError

if TYPE_CHECKING:
    from fablestar.agents.manager import AgentState
    from fablestar.server import FablestarServer

logger = logging.getLogger(__name__)

VOICE_COOLDOWN_S = 20.0
VOICE_MAX_CHARS = 200
# '<Speaker> says: "message"' — the say broadcast shape.
SAY_LINE = re.compile(r'^(?P<speaker>[^:]{1,60}) says: "(?P<message>.*)"$')


def sanitize_utterance(text: str) -> str:
    """One line, no quotes/newlines/command-ish prefixes, hard length cap."""
    line = " ".join(text.replace("\r", " ").replace("\n", " ").split())
    line = line.strip().strip('"').strip()
    line = re.sub(r"^[/@!>\.]+", "", line).strip()
    # Never let a reply smuggle a say-of-a-say chain.
    line = line.replace('"', "'")
    return line[:VOICE_MAX_CHARS]


def addressed_line(
    perceptions: list[str], agent_name: str, known_agent_names: set[str]
) -> tuple[str, str] | None:
    """
    Most recent say line from a NON-agent speaker that mentions this agent
    (first name or full name, case-insensitive). Returns (speaker, message).
    """
    first = agent_name.split()[0].lower()
    full = agent_name.lower()
    for text in reversed(perceptions):
        m = SAY_LINE.match(text)
        if not m:
            continue
        speaker = m.group("speaker").strip()
        if speaker == agent_name or speaker in known_agent_names or speaker == "You":
            continue
        message = m.group("message")
        low = message.lower()
        if first in low or full in low:
            return (speaker, message)
    return None


def voice_prompt(state: "AgentState", feelings_word: str, speaker: str, message: str) -> str:
    p = state.persona
    facts = "; ".join(p.hard_facts) if p.hard_facts else "none recorded"
    recent = " / ".join(state.session.recent_perceptions(6))
    return (
        f"You are {p.name}, a character in a space-station MUD. Stay strictly in character.\n"
        f"Hard facts about you (never contradict): {facts}.\n"
        f"You want: {p.wants}. You fear: {p.fears}. Speech style: {p.speech}.\n"
        f"Right now you feel {feelings_word}.\n"
        f"Recently: {recent}\n"
        f'{speaker} just said to you: "{message}"\n'
        "Reply with ONLY the words you speak aloud — one short line, no quotes, "
        "no narration, no stage directions."
    )


class AgentBrain:
    def __init__(self, server: "FablestarServer"):
        self.server = server
        self.llm = LLMClient(server.config.agents_llm)
        self._last_voice_at: dict[str, float] = {}

    @property
    def enabled(self) -> bool:
        return bool(self.server.config.agents_llm.enabled)

    async def maybe_voice(self, state: "AgentState") -> bool:
        """Reply if a player addressed this agent recently. Returns True on speech."""
        if not self.enabled:
            return False
        agent_id = state.persona.id
        now = time.monotonic()
        if now - self._last_voice_at.get(agent_id, 0.0) < VOICE_COOLDOWN_S:
            return False
        known = {s.persona.name for s in self.server.agent_manager.agents.values()}
        hit = addressed_line(state.session.recent_perceptions(10), state.persona.name, known)
        if hit is None:
            return False
        speaker, message = hit
        # Claim the cooldown before the (slow) call so one address = one reply.
        self._last_voice_at[agent_id] = now

        from fablestar.agents.feelings import mood_word

        stats = await self.server.redis.get_player_stats(state.persona.name)
        prompt = voice_prompt(state, mood_word(stats, state.persona), speaker, message)
        try:
            raw = await self.llm.generate_or_raise(
                prompt,
                system_prompt="You voice one MUD character. Output only their spoken words.",
                max_tokens=80,
            )
        except LLMGenerationError as exc:
            logger.info("Agent voice unavailable for %s: %s", agent_id, exc)
            self._record(state, prompt, f"[no reply: {exc}]")
            return False
        reply = sanitize_utterance(raw)
        if not reply:
            return False
        self._record(state, prompt, reply)
        await self.server.dispatcher.dispatch(state.session, f"say {reply}")
        return True

    def _record(self, state: "AgentState", prompt: str, response: Any) -> None:
        state.pov.append(
            {"at": time.time(), "kind": "voice", "prompt": prompt, "response": str(response)}
        )
        del state.pov[:-20]
