"""
AgentBrain — the LLM half: voice replies, budgeted banter, intent goals.

Uses the engine's secondary LLM profile (api.ai.profile), so a dead brain endpoint costs one
fast-fail and the Body keeps living on rules. All output is sanitized and re-enters the world only
as a plain `say` command through the dispatcher. Prompt wording is lexicon (agents.prompt.*), so
a world describes its own setting.
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from sage.api import PluginAPI, t

from .body import route_path
from .feelings import mood_word, recall

if TYPE_CHECKING:
    from .manager import AgentManager, AgentState

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
# The answer format stays in code: its JSON braces are not lexicon placeholders.
INTENT_FORMAT = (
    "Decide what to do next. Answer with ONLY one JSON object, no prose:\n"
    '{"goal": "wander_to|hunt|rest|talk|scavenge|sell|buy|idle", '
    '"target": "<see targets above>", '
    '"why": "<few words>", "say": "<one spoken line or empty>"}'
)


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


def _persona_vars(state: AgentState) -> dict[str, str]:
    p = state.persona
    return {
        "name": p.name,
        "setting": t("agents.prompt.setting"),
        "facts": "; ".join(p.hard_facts) if p.hard_facts else t("agents.prompt.none_recorded"),
        "wants": p.wants,
        "fears": p.fears,
        "speech": p.speech,
    }


def voice_prompt(
    state: AgentState,
    feelings_word: str,
    speaker: str,
    message: str,
    memories: list[str] | None = None,
) -> str:
    return t(
        "agents.prompt.voice",
        **_persona_vars(state),
        mood=feelings_word,
        memories=" / ".join(memories) if memories else t("agents.prompt.nothing_notable"),
        recent=" / ".join(state.session.recent_perceptions(6)),
        speaker=speaker,
        message=message,
    )


def intent_prompt(
    state: AgentState,
    feelings_word: str,
    known_rooms: list[str],
    memories: list[str],
    players_present: list[str],
    money: int = 0,
    currency: str = "",
    sellables: list[str] | None = None,
) -> str:
    body = t(
        "agents.prompt.intent",
        **_persona_vars(state),
        mood=feelings_word,
        people=", ".join(players_present) if players_present else t("agents.prompt.nobody"),
        money=money,
        currency=currency,
        carrying=", ".join((sellables or [])[:4]) if sellables else t("agents.prompt.no_goods"),
        memories=" / ".join(memories) if memories else t("agents.prompt.nothing_notable"),
        recent=" / ".join(state.session.recent_perceptions(8)),
        rooms=", ".join(known_rooms[:14]) if known_rooms else t("agents.prompt.no_rooms"),
        world_notes=t("agents.prompt.world_notes"),
    )
    return f"{body}\n{INTENT_FORMAT}"


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
    default_buy: str = "",
) -> tuple[str, list[str]] | None:
    """
    Pure: intent dict -> (goal_label, command list) for the Body, or None when
    the goal can't be realised (unreachable room, unknown entity, plain idle).
    """
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
        item = (target or default_buy).strip().lower()
        room_id = seller_room_finder(item) if seller_room_finder and item else None
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
            # zone: resolve the slug against the map.
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
    def __init__(self, api: PluginAPI, manager: AgentManager):
        self.api = api
        self.manager = manager
        self._last_voice_at: dict[str, float] = {}
        self._answered_lines: dict[str, tuple[str, str]] = {}
        self._last_banter_at: dict[str, float] = {}
        self._pair_last: dict[tuple[str, str], float] = {}
        self._pair_reply_pending: dict[tuple[str, str], str] = {}
        self._last_intent_at: dict[str, float] = {}
        self._intent_busy = False  # budget: one intent generation at a time

    @property
    def enabled(self) -> bool:
        return self.api.ai.profile().enabled

    async def _generate(self, prompt: str, system_key: str, max_tokens: int) -> str:
        return await self.api.ai.profile().generate(
            prompt, system_prompt=t(system_key), max_tokens=max_tokens
        )

    def _pair_key(self, a: str, b: str) -> tuple[str, str]:
        return (a, b) if a <= b else (b, a)

    async def maybe_voice(self, state: AgentState, social_ok: bool = False) -> bool:
        """Reply if someone addressed this agent recently. Agent speakers only
        count in social rooms (social_ok) and burn the pair budget."""
        if not self.enabled:
            return False
        agent_id = state.persona.id
        now = time.monotonic()
        if now - self._last_voice_at.get(agent_id, 0.0) < VOICE_COOLDOWN_S:
            return False
        known = {s.persona.name for s in self.manager.agents.values()}
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

        stats = await self.api.characters.stats(state.persona.name)
        prompt = voice_prompt(
            state, mood_word(stats, state.persona), speaker, message, recall(stats, 6)
        )
        try:
            raw = await self._generate(prompt, "agents.prompt.voice_system", 80)
        except Exception as exc:
            logger.info("Agent voice unavailable for %s: %s", agent_id, exc)
            self._record(state, prompt, f"[no reply: {exc}]")
            return False
        reply = sanitize_utterance(raw)
        if not reply:
            return False
        self._record(state, prompt, reply)
        self.api.telemetry.event(
            "voice", agent=state.persona.id, to=speaker, heard=message[:120], reply=reply
        )
        await self.api.sessions.dispatch(state.session, f"say {reply}")
        return True

    async def maybe_banter(self, state: AgentState, other_name: str) -> bool:
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
            stats = await self.api.characters.stats(me)
            p = state.persona
            other_first = other_name.split()[0]
            prompt = t(
                "agents.prompt.banter",
                name=p.name,
                place=t("agents.prompt.banter_place"),
                mood=mood_word(stats, p),
                speech=p.speech,
                memories=" / ".join(recall(stats, 4)) or t("agents.prompt.nothing_notable"),
                other=other_name,
                other_first=other_first,
            )
            try:
                raw = await self._generate(prompt, "agents.prompt.voice_system", 60)
            except Exception as exc:
                logger.info("Banter unavailable for %s: %s", me, exc)
                return False
            line = sanitize_utterance(raw)
            if not line:
                return False
            if other_first.lower() not in line.lower():
                line = f"{other_first}, {line}"
            self._record(state, prompt, line, kind="banter")
            self.api.telemetry.event("banter", agent=state.persona.id, to=other_name, line=line)
            self._pair_reply_pending[key] = other_name
            await self.api.sessions.dispatch(state.session, f"say {line}")
            return True
        finally:
            self._intent_busy = False

    async def maybe_intent(
        self, state: AgentState, players_present: list[str], known_rooms: list[str]
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
            stats = await self.api.characters.stats(state.persona.name)
            inventory = await self.api.inventory.get(state.persona.name)
            equipped_ids = {
                (it or {}).get("id") for it in (stats.get("equipment") or {}).values() if it
            }
            sellables = [
                it.get("name", "?")
                for it in inventory
                if it.get("id") not in equipped_ids and int(it.get("value", 0) or 0) > 0
            ]
            wallet = self.api.wallet
            prompt = intent_prompt(
                state,
                mood_word(stats, state.persona),
                known_rooms,
                recall(stats, 8),
                players_present,
                money=wallet.balance(stats),
                currency=wallet.name() if wallet.enabled else "",
                sellables=sellables,
            )
            try:
                raw = await self._generate(prompt, "agents.prompt.intent_system", 120)
            except Exception as exc:
                logger.info("Agent intent unavailable for %s: %s", agent_id, exc)
                self._record(state, prompt, f"[no intent: {exc}]", kind="intent")
                return None
            intent = parse_intent(raw)
            self._record(state, prompt, raw if intent else f"[unparsed] {raw}", kind="intent")
            if intent is None:
                self.api.telemetry.event("intent_unparsed", agent=agent_id, raw=raw[:200])
            return intent
        finally:
            self._intent_busy = False

    def _record(self, state: AgentState, prompt: str, response: Any, kind: str = "voice") -> None:
        state.pov.append(
            {"at": time.time(), "kind": kind, "prompt": prompt, "response": str(response)}
        )
        del state.pov[:-20]
