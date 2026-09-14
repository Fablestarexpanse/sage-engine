"""Admin/session commands — quit, and in-game admin shortcuts."""

from sage.commands.registry import command
from sage.network.session import Session


@command("quit", aliases=["exit", "logout", "disconnect"])
async def quit_cmd(session: Session, args: list[str]):
    """Save and disconnect from the server."""
    # The server loop notices the closed socket and saves/cleans up.
    from sage import lexicon

    await session.end("quit", lexicon.t("session.goodbye"))
