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
# Agent-to-agent chat is an infinite-loop hazard: hard budgets only.
BANTER_INIT_COOLDOWN_S = 300.0  # one opener per agent per 5 min
BANTER_PAIR_COOLDOWN_S = 600.0  # one exchange per pair per 10 min
INTENT_COOLDOWN_S = 90.0
INTENT_GOALS = ("wander_to", "hunt", "rest", "talk", "scavenge", "sell", "buy", "idle")
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
    perceptions: list[str],
    agent_name: str,
    known_agent_names: set[str],
    allow_agent_speakers: bool = False,
) -> tuple[str, str] | None:
    """
    Most recent say line that mentions this agent (first or full name,
    case-insensitive). Agent speakers are ignored unless allow_agent_speakers
    (social rooms), so the world never chats itself into a loop by default.
    Returns (speaker, message).
    """
    first = agent_name.split()[0].lower()
    full = agent_name.lower()
    for text in reversed(perceptions):
        m = SAY_LINE.match(text)
        if not m:
            continue
        speaker = m.group("speaker").strip()
        if speaker == agent_name or speaker == "You":
            continue
        if speaker in known_agent_names and not allow_agent_speakers:
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
    digi: int = 0,
    sellables: list[str] | None = None,
) -> str:
    p = state.persona
    facts = "; ".join(p.hard_facts) if p.hard_facts else "none recorded"
    recent = " / ".join(state.session.recent_perceptions(8))
    remembered = " / ".join(memories) if memories else "nothing notable"
    rooms = ", ".join(known_rooms[:14]) if known_rooms else "nowhere new"
    people = ", ".join(players_present) if players_present else "nobody"
    carrying = ", ".join((sellables or [])[:4]) if sellables else "nothing worth selling"
    return (
        f"You are {p.name}, a character in a space-station MUD.\n"
        f"Hard facts (never contradict): {facts}.\n"
        f"You want: {p.wants}. You fear: {p.fears}.\n"
        f"You feel {feelings_word}. Present with you: {people}.\n"
        f"You carry {digi} Digi. Sellable goods on you: {carrying}.\n"
        f"You remember: {remembered}\n"
        f"Recently: {recent}\n"
        f"Rooms you know: {rooms}.\n"
        "Shops: the pawn_shop buys salvage; the general_store sells food; "
        "scavenging the wilds finds sellable goods.\n"
        "Goals and their targets: wander_to -> a room from the list above; "
        "hunt -> a creature (razor crab, rust hound, scrap drone); "
        "buy -> an item (ration, stout, charge cell); rest/scavenge/sell/idle -> empty.\n"
        "Decide what to do next. Answer with ONLY one JSON object, no prose:\n"
        '{"goal": "wander_to|hunt|rest|talk|scavenge|sell|buy|idle", '
        '"target": "<see targets above>", '
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
    buyer_room_finder: Callable[[], str | None] | None = None,
    seller_room_finder: Callable[[str], str | None] | None = None,
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
    if goal == "sell":
        room_id = buyer_room_finder() if buyer_room_finder else None
        if room_id is None:
            return None
        path = route_path(current_room, room_id, exits_of)
        if path is None:
            return None
        return ("sell salvage", [*path, "sell all"])
    if goal == "buy":
        item = (target or "ration").strip().lower()
        room_id = seller_room_finder(item) if seller_room_finder else None
        if room_id is None:
            return None
        path = route_path(current_room, room_id, exits_of)
        if path is None:
            return None
        return (f"buy {item[:20]}", [*path, f"buy {item}"])
    if goal == "talk":
        line = sanitize_utterance(intent.get("say") or target)
        return (f"talk: {line[:40]}", [f"say {line}"]) if line else None
    if goal == "wander_to":
        slug = target.split(":")[-1].strip().replace(" ", "_").lower()
        if not slug:
            return None
        room_id = target if ":" in target else f"{zone}:{slug}"
        if room_id not in exits_of:
            # Known rooms are offered as bare slugs and can live in another
            # zone (the AIpub apartments): resolve the slug against the map.
            room_id = next((r for r in exits_of if r.split(":")[-1] == slug), room_id)
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
        self._answered_lines: dict[str, tuple[str, str]] = {}
        self._last_banter_at: dict[str, float] = {}
        self._pair_last: dict[tuple[str, str], float] = {}
        self._pair_reply_pending: dict[tuple[str, str], str] = {}
        self._last_intent_at: dict[str, float] = {}
        self._intent_busy = False  # budget: one intent generation at a time

    def _build_client(self, config):
        if (config.primary_backend or "").lower().strip() == "embedded":
            # Shared server instance: narration and agent brains use ONE
            # loaded GGUF instead of two copies in RAM.
            getter = getattr(self.server, "embedded_llm", None)
            if callable(getter):
                shared = getter()
                shared.reconfigure(config)
                return shared
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

    def _pair_key(self, a: str, b: str) -> tuple[str, str]:
        return (a, b) if a <= b else (b, a)

    async def maybe_voice(self, state: "AgentState", social_ok: bool = False) -> bool:
        """Reply if someone addressed this agent recently. Agent speakers only
        count in social rooms (social_ok) and burn the pair budget."""
        if not self.enabled:
            return False
        agent_id = state.persona.id
        now = time.monotonic()
        if now - self._last_voice_at.get(agent_id, 0.0) < VOICE_COOLDOWN_S:
            return False
        known = {s.persona.name for s in self.server.agent_manager.agents.values()}
        hit = addressed_line(
            state.session.recent_perceptions(10),
            state.persona.name,
            known,
            allow_agent_speakers=social_ok,
        )
        if hit is None:
            return False
        speaker, message = hit
        if speaker in known:
            # Agent speaker: reply exactly once, and only to a pending opener
            # this banter budget created. Replies never re-trigger.
            key = self._pair_key(state.persona.name, speaker)
            if self._pair_reply_pending.get(key) != state.persona.name:
                return False
            del self._pair_reply_pending[key]
        # The same perception line lingers in the buffer past the cooldown —
        # never answer one address twice.
        if self._answered_lines.get(agent_id) == (speaker, message):
            return False
        self._answered_lines[agent_id] = (speaker, message)
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
        from fablestar.telemetry import log_event

        log_event("voice", agent=state.persona.id, to=speaker, heard=message[:120], reply=reply)
        await self.server.dispatcher.dispatch(state.session, f"say {reply}")
        return True

    async def maybe_banter(self, state: "AgentState", other_name: str) -> bool:
        """Open one budgeted exchange with another agent in a social room."""
        if not self.enabled or self._intent_busy:
            return False
        me = state.persona.name
        now = time.monotonic()
        if now - self._last_banter_at.get(me, 0.0) < BANTER_INIT_COOLDOWN_S:
            return False
        key = self._pair_key(me, other_name)
        if now - self._pair_last.get(key, 0.0) < BANTER_PAIR_COOLDOWN_S:
            return False
        # Claim budgets before the slow call.
        self._last_banter_at[me] = now
        self._pair_last[key] = now
        self._intent_busy = True
        try:
            from fablestar.agents.feelings import mood_word, recall

            stats = await self.server.redis.get_player_stats(me)
            p = state.persona
            other_first = other_name.split()[0]
            prompt = (
                f"You are {p.name} in the AIpub on Tidegate Isle. "
                f"You feel {mood_word(stats, p)}. Speech style: {p.speech}.\n"
                f"You remember: {' / '.join(recall(stats, 4)) or 'nothing notable'}\n"
                f"{other_name} is here. Say ONE short line of pub small talk to them "
                f"that includes the name {other_first}. Output only the spoken words."
            )
            try:
                raw = await self.llm.generate_or_raise(
                    prompt,
                    system_prompt="You voice one MUD character. Output only their spoken words.",
                    max_tokens=60,
                )
            except LLMGenerationError as exc:
                logger.info("Banter unavailable for %s: %s", me, exc)
                return False
            line = sanitize_utterance(raw)
            if not line:
                return False
            if other_first.lower() not in line.lower():
                line = f"{other_first}, {line}"
            self._record(state, prompt, line, kind="banter")
            from fablestar.telemetry import log_event

            log_event("banter", agent=state.persona.id, to=other_name, line=line)
            self._pair_reply_pending[key] = other_name
            await self.server.dispatcher.dispatch(state.session, f"say {line}")
            return True
        finally:
            self._intent_busy = False

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
            inventory = await self.server.redis.get_player_inventory(state.persona.name)
            equipped_ids = {
                (it or {}).get("id") for it in (stats.get("equipment") or {}).values() if it
            }
            sellables = [
                it.get("name", "?")
                for it in inventory
                if it.get("id") not in equipped_ids and int(it.get("value", 0) or 0) > 0
            ]
            prompt = intent_prompt(
                state,
                mood_word(stats, state.persona),
                known_rooms,
                recall(stats, 8),
                players_present,
                digi=int(stats.get("digi", 0) or 0),
                sellables=sellables,
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
            if intent is None:
                from fablestar.telemetry import log_event

                log_event("intent_unparsed", agent=agent_id, raw=raw[:200])
            return intent
        finally:
            self._intent_busy = False

    def _record(self, state: "AgentState", prompt: str, response: Any, kind: str = "voice") -> None:
        state.pov.append(
            {"at": time.time(), "kind": kind, "prompt": prompt, "response": str(response)}
        )
        del state.pov[:-20]
