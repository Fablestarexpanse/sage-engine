"""
AgentBrain — the LLM half. Voice replies (M3); intent goals (M4).

Own LLMClient on config.agents_llm (separate endpoint + its own circuit
breaker), so a dead brain endpoint costs one fast-fail and the Body keeps
living on rules. All output is sanitized and re-enters the world only as a
plain `say` command through the dispatcher.
"""

import json
import logging
import re
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from fablestar.llm.client import LLMClient, LLMGenerationError

if TYPE_CHECKING:
    from fablestar.agents.manager import AgentState
    from fablestar.server import FablestarServer

logger = logging.getLogger(__name__)

VOICE_COOLDOWN_S = 20.0
VOICE_MAX_CHARS = 200
INTENT_COOLDOWN_S = 90.0
INTENT_GOALS = ("wander_to", "hunt", "rest", "talk", "scavenge", "idle")
_JSON_BLOB = re.compile(r"\{.*\}", re.DOTALL)
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


def voice_prompt(
    state: "AgentState",
    feelings_word: str,
    speaker: str,
    message: str,
    memories: list[str] | None = None,
) -> str:
    p = state.persona
    facts = "; ".join(p.hard_facts) if p.hard_facts else "none recorded"
    recent = " / ".join(state.session.recent_perceptions(6))
    remembered = " / ".join(memories) if memories else "nothing notable"
    return (
        f"You are {p.name}, a character in a space-station MUD. Stay strictly in character.\n"
        f"Hard facts about you (never contradict): {facts}.\n"
        f"You want: {p.wants}. You fear: {p.fears}. Speech style: {p.speech}.\n"
        f"Right now you feel {feelings_word}.\n"
        f"You remember: {remembered}\n"
        f"Recently: {recent}\n"
        f'{speaker} just said to you: "{message}"\n'
        "Reply with ONLY the words you speak aloud — one short line, no quotes, "
        "no narration, no stage directions."
    )


def intent_prompt(
    state: "AgentState",
    feelings_word: str,
    known_rooms: list[str],
    memories: list[str],
    players_present: list[str],
) -> str:
    p = state.persona
    facts = "; ".join(p.hard_facts) if p.hard_facts else "none recorded"
    recent = " / ".join(state.session.recent_perceptions(8))
    remembered = " / ".join(memories) if memories else "nothing notable"
    rooms = ", ".join(known_rooms[:14]) if known_rooms else "nowhere new"
    people = ", ".join(players_present) if players_present else "nobody"
    return (
        f"You are {p.name}, a character in a space-station MUD.\n"
        f"Hard facts (never contradict): {facts}.\n"
        f"You want: {p.wants}. You fear: {p.fears}.\n"
        f"You feel {feelings_word}. Present with you: {people}.\n"
        f"You remember: {remembered}\n"
        f"Recently: {recent}\n"
        f"Rooms you know: {rooms}.\n"
        "Decide what to do next. Answer with ONLY one JSON object, no prose:\n"
        '{"goal": "wander_to|hunt|rest|talk|scavenge|idle", '
        '"target": "<room slug, entity, or empty>", '
        '"why": "<few words>", "say": "<one spoken line or empty>"}'
    )


def parse_intent(raw: str) -> dict[str, str] | None:
    """Strict-ish parse: first {...} blob, valid JSON, known goal. None on failure."""
    m = _JSON_BLOB.search(raw)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    goal = str(data.get("goal", "")).strip().lower()
    if goal not in INTENT_GOALS:
        return None
    return {
        "goal": goal,
        "target": str(data.get("target", "") or "").strip(),
        "why": str(data.get("why", "") or "").strip()[:120],
        "say": str(data.get("say", "") or "").strip(),
    }


def compile_goal(
    intent: dict[str, str],
    current_room: str,
    zone: str,
    exits_of: dict[str, dict[str, str]],
    entity_room_finder: Callable[[str], str | None],
) -> tuple[str, list[str]] | None:
    """
    Pure: intent dict -> (goal_label, command list) for the Body, or None when
    the goal can't be realised (unreachable room, unknown entity, plain idle).
    """
    from fablestar.agents.body import route_path

    goal = intent["goal"]
    target = intent["target"]
    if goal == "idle":
        return None
    if goal == "rest":
        return ("rest", ["rest"])
    if goal == "scavenge":
        return ("scavenge", ["search"])
    if goal == "talk":
        line = sanitize_utterance(intent.get("say") or target)
        return (f"talk: {line[:40]}", [f"say {line}"]) if line else None
    if goal == "wander_to":
        slug = target.split(":")[-1].strip().replace(" ", "_").lower()
        if not slug:
            return None
        room_id = target if ":" in target else f"{zone}:{slug}"
        path = route_path(current_room, room_id, exits_of)
        if not path:  # unreachable or already there
            return None
        return (f"wander_to {slug}", path)
    if goal == "hunt":
        room_id = entity_room_finder(target.lower()) if target else None
        if room_id is None:
            return None
        path = route_path(current_room, room_id, exits_of) or []
        # Arriving is enough — the fight reflex takes over on sight.
        return (f"hunt {target[:30]}", path) if path else None
    return None


class AgentBrain:
    def __init__(self, server: "FablestarServer"):
        self.server = server
        self.llm = self._build_client(server.config.agents_llm)
        self._last_voice_at: dict[str, float] = {}
        self._last_intent_at: dict[str, float] = {}
        self._intent_busy = False  # budget: one intent generation at a time

    @staticmethod
    def _build_client(config):
        if (config.primary_backend or "").lower().strip() == "embedded":
            from fablestar.agents.embedded_llm import EmbeddedLLM

            return EmbeddedLLM(config)
        return LLMClient(config)

    def reconfigure(self, config) -> None:
        """Apply new brain settings live (admin panel save)."""
        self.server.config.agents_llm = config
        current_embedded = type(self.llm).__name__ == "EmbeddedLLM"
        want_embedded = (config.primary_backend or "").lower().strip() == "embedded"
        if current_embedded != want_embedded:
            self.llm = self._build_client(config)
        elif want_embedded:
            self.llm.reconfigure(config)
        else:
            self.llm.reconfigure(config)

    def status(self) -> dict:
        cfg = self.server.config.agents_llm
        base = {
            "enabled": bool(cfg.enabled),
            "backend": cfg.primary_backend,
            "chat_model": cfg.chat_model,
            "lm_studio_url": cfg.lm_studio_url,
            "ollama_url": cfg.ollama_url,
            "model_path": cfg.model_path,
            "temperature": cfg.temperature,
            "timeout_seconds": cfg.timeout_seconds,
        }
        if hasattr(self.llm, "status"):
            base["embedded"] = self.llm.status()
        return base

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

        from fablestar.agents.feelings import mood_word, recall

        stats = await self.server.redis.get_player_stats(state.persona.name)
        prompt = voice_prompt(
            state, mood_word(stats, state.persona), speaker, message, recall(stats, 6)
        )
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

    async def maybe_intent(
        self, state: "AgentState", players_present: list[str], known_rooms: list[str]
    ) -> dict[str, str] | None:
        """
        Ask the brain "what do you want?" when idle near players. Returns the
        parsed intent dict (manager compiles it) or None. Budget: one
        generation in flight across all agents; 90s cooldown per agent.
        """
        if not self.enabled or self._intent_busy:
            return None
        agent_id = state.persona.id
        now = time.monotonic()
        if now - self._last_intent_at.get(agent_id, 0.0) < INTENT_COOLDOWN_S:
            return None
        self._last_intent_at[agent_id] = now  # claim before the slow call
        self._intent_busy = True
        try:
            from fablestar.agents.feelings import mood_word, recall

            stats = await self.server.redis.get_player_stats(state.persona.name)
            prompt = intent_prompt(
                state,
                mood_word(stats, state.persona),
                known_rooms,
                recall(stats, 8),
                players_present,
            )
            try:
                raw = await self.llm.generate_or_raise(
                    prompt,
                    system_prompt="You decide one MUD character's next goal. "
                    "Output only a single JSON object.",
                    max_tokens=120,
                )
            except LLMGenerationError as exc:
                logger.info("Agent intent unavailable for %s: %s", agent_id, exc)
                self._record(state, prompt, f"[no intent: {exc}]", kind="intent")
                return None
            intent = parse_intent(raw)
            self._record(state, prompt, raw if intent else f"[unparsed] {raw}", kind="intent")
            return intent
        finally:
            self._intent_busy = False

    def _record(self, state: "AgentState", prompt: str, response: Any, kind: str = "voice") -> None:
        state.pov.append(
            {"at": time.time(), "kind": kind, "prompt": prompt, "response": str(response)}
        )
        del state.pov[:-20]
