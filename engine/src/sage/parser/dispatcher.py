"""CommandDispatcher — tokenises raw input and routes it to the registered handler."""

import difflib
import logging
import re
import time

from sage.commands.registry import registry
from sage.network.session import Session
from sage.parser.tokenizer import tokenize

logger = logging.getLogger(__name__)

MAX_INPUT_CHARS = 1000
ECHO_CHARS = 40
# Token bucket per session: sustained commands/second and burst size.
RATE_PER_S = 8.0
RATE_BURST = 20.0
# Never run these from an abbreviation; a stray "q" must not end the session.
NO_PREFIX_COMMANDS = frozenset({"quit"})

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def clean_input(raw_input: str) -> str:
    """Cap length and strip terminal control characters (ANSI escapes, bells, CR).

    Newlines and tabs become spaces so a pasted block stays one command.
    """
    text = raw_input[:MAX_INPUT_CHARS].replace("\n", " ").replace("\t", " ")
    return _CONTROL_CHARS.sub("", text).strip()


def split_verb(text: str) -> tuple[str, str]:
    """First word and the untouched remainder, preserving the player's case."""
    parts = text.split(None, 1)
    if not parts:
        return "", ""
    return parts[0], parts[1] if len(parts) > 1 else ""


def _resolve_verb(verb: str):
    """Exact name/alias, else a unique command-name prefix. Returns (command, suggestions)."""
    command = registry.get(verb)
    if command:
        return command, []
    names = sorted(registry._commands)
    starts = [n for n in names if n.startswith(verb)]
    if len(starts) == 1 and len(verb) >= 2 and starts[0] not in NO_PREFIX_COMMANDS:
        return registry.get(starts[0]), []
    if starts:
        return None, starts[:5]
    return None, difflib.get_close_matches(
        verb, names + sorted(registry._aliases), n=3, cutoff=0.75
    )


class CommandDispatcher:
    """
    Routes user input to the appropriate command handler.
    """

    def _allow(self, session: Session) -> bool:
        if getattr(session, "is_agent", False):
            return True
        now = time.monotonic()
        tokens = getattr(session, "_rate_tokens", RATE_BURST)
        last = getattr(session, "_rate_at", now)
        tokens = min(RATE_BURST, tokens + (now - last) * RATE_PER_S)
        session._rate_at = now
        if tokens < 1.0:
            session._rate_tokens = tokens
            return False
        session._rate_tokens = tokens - 1.0
        session._rate_warned = False
        return True

    async def dispatch(self, session: Session, raw_input: str):
        """Parse and execute a command for a given session."""
        text = clean_input(raw_input or "")
        if not text:
            return

        if not self._allow(session):
            if not getattr(session, "_rate_warned", False):
                session._rate_warned = True
                await session.send(
                    "Slow down — commands are arriving faster than the world can act."
                )
            return

        tokens = tokenize(text)
        if not tokens:
            return

        verb = tokens[0]
        args = tokens[1:]
        # Free-text commands (say, tell, emote) read this to keep the player's case.
        session.raw_args = split_verb(text)[1]

        command, suggestions = _resolve_verb(verb)

        if command:
            try:
                await command.handler(session, args)
            except Exception as e:
                logger.error(f"Error executing command '{verb}': {e}")
                await session.send("An error occurred while processing your command.")
        else:
            shown = verb if len(verb) <= ECHO_CHARS else verb[:ECHO_CHARS] + "…"
            hint = f" Did you mean: {', '.join(suggestions)}?" if suggestions else ""
            await session.send(f"Unknown command: '{shown}'.{hint} Type 'help' for assistance.")
