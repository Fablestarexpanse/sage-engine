"""Player moderation: address bans, sign-in history, mutes, the report queue and registration lock.

Settings live in config/moderation.toml (``server.config.moderation``). Recording the address a
player signs in from is off by default; while it is off, sign-in rows are still kept (when, how)
but without an address, and addresses already stored are left to age out or be erased by staff.

Addresses come from the connection itself (the peer the server sees). Behind a reverse proxy that
is the proxy's address, so bans and history need the proxy to pass the real client through at the
network level; forwarded headers are not trusted here because any client can send them.
"""

from __future__ import annotations

import ipaddress
import logging
import time
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select, update

logger = logging.getLogger(__name__)

REPORT_STATUSES = ("open", "fixed", "wont_fix", "duplicate")
MAX_REPORT_LENGTH = 2000


def settings(server: Any) -> Any:
    from sage.core.config import ModerationConfig

    return getattr(server.config, "moderation", None) or ModerationConfig()


def parse_network(text: str) -> str:
    """A normalised address or CIDR range; ValueError when it is neither."""
    raw = (text or "").strip()
    if not raw:
        raise ValueError("network_required")
    try:
        return str(ipaddress.ip_network(raw, strict=False))
    except ValueError:
        raise ValueError(f"not_an_address_or_range: {raw}") from None


def _address(value: str | None) -> Any:
    """The address as an ip_address; an IPv4 address carried in IPv6 (::ffff:a.b.c.d) as IPv4."""
    try:
        ip = ipaddress.ip_address((value or "").strip())
    except ValueError:
        return None
    return getattr(ip, "ipv4_mapped", None) or ip


async def active_ban(server: Any, address: str | None) -> dict[str, Any] | None:
    """The ban covering ``address`` (not expired), or None. Unparseable addresses are never banned."""
    from sage.state.models import AddressBan

    ip = _address(address)
    if ip is None:
        return None
    now = datetime.utcnow()
    async with server.db.session_factory() as session:
        bans = (await session.execute(select(AddressBan))).scalars().all()
    for ban in bans:
        if ban.expires_at is not None and ban.expires_at <= now:
            continue
        try:
            if ip in ipaddress.ip_network(ban.network, strict=False):
                return {"id": ban.id, "network": ban.network, "reason": ban.reason}
        except ValueError:
            continue
    return None


async def record_login(server: Any, account_id: int, method: str, address: str | None) -> None:
    """Add a sign-in row; the address only while recording is on. Never fails the sign-in."""
    from sage.state.models import AccountLogin

    keep = settings(server).record_login_addresses and _address(address) is not None
    try:
        async with server.db.session_factory() as session:
            session.add(
                AccountLogin(
                    account_id=account_id,
                    method=method[:16],
                    address=str(_address(address)) if keep else None,
                )
            )
            await session.commit()
    except Exception:
        logger.warning("Could not record sign-in for account %s", account_id, exc_info=True)


async def purge_history(server: Any) -> int:
    """Delete sign-in rows older than the retention period. Returns how many went."""
    from sage.state.models import AccountLogin

    cutoff = datetime.utcnow() - timedelta(days=settings(server).login_history_days)
    async with server.db.session_factory() as session:
        result = await session.execute(delete(AccountLogin).where(AccountLogin.at < cutoff))
        await session.commit()
    return int(result.rowcount or 0)


async def erase_addresses(server: Any, account_id: int | None = None) -> int:
    """Blank stored addresses (one account's, or everyone's). Returns how many rows changed."""
    from sage.state.models import AccountLogin

    stmt = update(AccountLogin).where(AccountLogin.address.is_not(None)).values(address=None)
    if account_id is not None:
        stmt = stmt.where(AccountLogin.account_id == account_id)
    async with server.db.session_factory() as session:
        result = await session.execute(stmt)
        await session.commit()
    return int(result.rowcount or 0)


async def login_history(
    server: Any,
    *,
    account_id: int | None = None,
    address: str = "",
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """Sign-ins newest first, by account or by address (an address or a CIDR range)."""
    from sage.state.models import Account, AccountLogin

    stmt = select(AccountLogin, Account.username).join(
        Account, Account.id == AccountLogin.account_id
    )
    if account_id is not None:
        stmt = stmt.where(AccountLogin.account_id == account_id)
    if address:
        network = ipaddress.ip_network(parse_network(address), strict=False)
        if network.num_addresses == 1:
            stmt = stmt.where(AccountLogin.address == str(network.network_address))
        else:
            stmt = stmt.where(AccountLogin.address.is_not(None))
    async with server.db.session_factory() as session:
        rows = (await session.execute(stmt.order_by(AccountLogin.at.desc()))).all()
    if address and "/" in address:
        network = ipaddress.ip_network(parse_network(address), strict=False)
        rows = [r for r in rows if _address(r[0].address) in network]
    page = rows[max(0, offset) : max(0, offset) + max(1, min(limit, 500))]
    return {
        "total": len(rows),
        "rows": [
            {
                "id": login.id,
                "account_id": login.account_id,
                "account": username,
                "at": login.at.isoformat() + "Z",
                "method": login.method,
                "address": login.address,
            }
            for login, username in page
        ],
    }


# --- mutes -----------------------------------------------------------------------------------


def is_muted(session: Any) -> bool:
    until = getattr(session, "muted_until", None)
    return until is not None and until > datetime.utcnow()


async def set_mute(
    server: Any, account_id: int, minutes: int | None, reason: str = ""
) -> dict[str, Any]:
    """Mute an account for ``minutes`` (None lifts it). Connected characters are told at once."""
    from sage.state.models import Account, Character

    until = None if minutes is None else datetime.utcnow() + timedelta(minutes=int(minutes))
    async with server.db.session_factory() as session:
        account = await session.get(Account, account_id)
        if account is None:
            raise LookupError("account_not_found")
        account.muted_until = until
        account.mute_reason = ((reason or "").strip()[:500] or None) if until else None
        names = list(
            (
                await session.execute(
                    select(Character.name).where(Character.account_id == account_id)
                )
            ).scalars()
        )
        await session.commit()
    for name in names:
        live = server.session_manager.get_session_by_player(name)
        if live is not None:
            live.muted_until = until
            try:
                await live.say("moderation.muted_now" if until else "moderation.unmuted")
            except Exception:
                pass
    return {
        "account_id": account_id,
        "muted_until": until.isoformat() + "Z" if until else None,
        "characters_told": [n for n in names if server.session_manager.get_session_by_player(n)],
    }


# --- reports ---------------------------------------------------------------------------------

_last_report: dict[str, float] = {}


async def file_report(server: Any, session: Any, text: str) -> tuple[str, int | None]:
    """Store a report from a playing character. Returns (lexicon key to tell them, report id)."""
    from sage.state.models import PlayerReport

    text = (text or "").strip()
    if not text:
        return "report.usage", None
    name = session.player_id
    cooldown = settings(server).report_cooldown_seconds
    now = time.monotonic()
    if cooldown and now - _last_report.get(name, -1e9) < cooldown:
        return "report.too_soon", None
    room_id = await server.redis.get_player_location(name) or ""
    async with server.db.session_factory() as db:
        row = PlayerReport(
            account_id=getattr(session, "account_id", None),
            character_name=name[:50],
            room_id=room_id[:255],
            text=text[:MAX_REPORT_LENGTH],
            status="open",
        )
        db.add(row)
        await db.commit()
        report_id = row.id
    _last_report[name] = now
    feed = getattr(server, "staff_feed", None)
    if feed is not None:
        feed.add(
            "report",
            f"Report #{report_id} from {name}: {text[:120]}",
            player=name,
            room_id=room_id,
            href="#/reports",
        )
    return "report.thanks", report_id


async def reports(
    server: Any, *, status: str = "open", limit: int = 50, offset: int = 0
) -> dict[str, Any]:
    from sage.state.models import PlayerReport

    stmt = select(PlayerReport)
    if status and status != "all":
        stmt = stmt.where(PlayerReport.status == status)
    async with server.db.session_factory() as session:
        total = await session.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = (
            await session.execute(
                stmt.order_by(PlayerReport.created_at.desc())
                .limit(max(1, min(limit, 500)))
                .offset(max(0, offset))
            )
        ).scalars()
        counts = dict(
            (
                await session.execute(
                    select(PlayerReport.status, func.count()).group_by(PlayerReport.status)
                )
            ).all()
        )
        return {
            "total": int(total or 0),
            "counts": {s: int(counts.get(s, 0)) for s in REPORT_STATUSES},
            "rows": [
                {
                    "id": r.id,
                    "at": r.created_at.isoformat() + "Z",
                    "account_id": r.account_id,
                    "character": r.character_name,
                    "room_id": r.room_id,
                    "text": r.text,
                    "status": r.status,
                    "staff_note": r.staff_note,
                    "handled_by": r.handled_by,
                    "handled_at": r.handled_at.isoformat() + "Z" if r.handled_at else None,
                }
                for r in rows
            ],
        }


async def update_report(
    server: Any, report_id: int, *, status: str | None, note: str | None, by: str
) -> dict[str, Any]:
    from sage.state.models import PlayerReport

    if status is not None and status not in REPORT_STATUSES:
        raise ValueError(f"unknown_status: {status}")
    async with server.db.session_factory() as session:
        row = await session.get(PlayerReport, report_id)
        if row is None:
            raise LookupError("report_not_found")
        if status is not None:
            row.status = status
        if note is not None:
            row.staff_note = note.strip()[:MAX_REPORT_LENGTH] or None
        row.handled_by = by[:64]
        row.handled_at = datetime.utcnow()
        await session.commit()
        return {"id": row.id, "status": row.status, "staff_note": row.staff_note}
