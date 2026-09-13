"""Admin/session commands — quit, and in-game admin shortcuts."""

from fablestar.commands.registry import command
from fablestar.network.session import Session


@command("quit", aliases=["exit", "logout", "disconnect"])
async def quit_cmd(session: Session, args: list[str]):
    """Save and disconnect from the server."""
    await session.send("Goodbye!")
    # The server loop will catch the disconnecting state and cleanup
    await session.close()
