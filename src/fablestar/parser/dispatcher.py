"""CommandDispatcher — tokenises raw input and routes it to the registered handler."""

import logging

from fablestar.commands.registry import registry
from fablestar.network.session import Session
from fablestar.parser.tokenizer import tokenize

logger = logging.getLogger(__name__)


class CommandDispatcher:
    """
    Routes user input to the appropriate command handler.
    """

    async def dispatch(self, session: Session, raw_input: str):
        """Parse and execute a command for a given session."""
        if not raw_input.strip():
            return

        tokens = tokenize(raw_input)
        if not tokens:
            return

        verb = tokens[0]
        args = tokens[1:]

        command = registry.get(verb)

        if command:
            try:
                # We'll pass session and args to the handler
                # Eventually, we might pass a 'CommandContext' object
                await command.handler(session, args)
            except Exception as e:
                logger.error(f"Error executing command '{verb}': {e}")
                await session.send("An error occurred while processing your command.")
        else:
            await session.send(f"Unknown command: '{verb}'. Type 'help' for assistance.")
