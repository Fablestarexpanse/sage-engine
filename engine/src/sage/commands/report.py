"""The report command: players send a bug, typo, idea or complaint to the staff queue."""

from sage.commands.registry import command
from sage.network.session import Session


@command("report", aliases=["bug", "typo", "idea"])
async def report(session: Session, args: list[str]):
    """Tell the staff about a bug, a typo, an idea or a problem. Usage: report <what happened>"""
    if not session.player_id:
        await session.say("session.not_authenticated")
        return
    from sage.app import app_instance
    from sage.services.moderation import file_report

    raw = getattr(session, "raw_args", None)
    text = raw.strip() if raw else " ".join(args)
    key, report_id = await file_report(app_instance, session, text)
    await session.say(key, id=report_id)
