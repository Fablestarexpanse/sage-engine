"""Search everything the console can open, for the Ctrl+K box: one query, results grouped by kind.

Each group runs only when the staff member has the tool for that kind, and every result carries
the console address (href) that opens it.
"""

from __future__ import annotations

import asyncio
from typing import Any

from sage.admin import character_tools, content_browser, player_accounts


def _match(needle: str, *fields: Any) -> bool:
    return any(needle in str(f).lower() for f in fields if f)


def _group(kind: str, label: str, hits: list[dict[str, Any]], limit: int) -> dict[str, Any]:
    return {"kind": kind, "label": label, "total": len(hits), "results": hits[:limit]}


def _content_groups(needle: str, limit: int, rooms: bool, items: bool, creatures: bool) -> list:
    groups = []
    if rooms:
        hits = []
        for zone, slug, data, error in content_browser.room_files():
            room_id = str(data.get("id") or f"{zone}:{slug}")
            if _match(needle, room_id, None if error else data.get("name")):
                hits.append(
                    {
                        "id": room_id,
                        "label": str(data.get("name") or slug),
                        "sub": room_id,
                        "href": f"#/content/rooms/{zone}/{slug}",
                    }
                )
        groups.append(_group("rooms", "Rooms", hits, limit))
    for kind, label, tab, wanted in (
        ("items", "Items", "items", items),
        ("entities", "Creatures", "creatures", creatures),
    ):
        if not wanted:
            continue
        hits = []
        for path, data, error in content_browser.template_files(kind):
            tid = str(data.get("id", path.stem)) if error is None else path.stem
            tags = data.get("tags") if isinstance(data.get("tags"), list) else []
            if _match(needle, tid, data.get("name"), *tags):
                kind_label = data.get("type")
                hits.append(
                    {
                        "id": tid,
                        "label": str(data.get("name") or tid),
                        "sub": f"{tid} · {kind_label}" if kind_label else tid,
                        "href": f"#/content/{tab}/{tid}",
                    }
                )
        groups.append(_group(kind, label, hits, limit))
    return groups


async def search(server: Any, ctx: Any, q: str, limit: int = 8) -> dict[str, Any]:
    needle = (q or "").strip().lower()
    if len(needle) < 2:
        return {"q": q, "groups": []}
    groups: list[dict[str, Any]] = []
    if ctx.may_use_tool("players"):
        chars = await character_tools.find(server, needle, limit)
        results = []
        for c in chars["rows"]:
            sub = f"{c['account']} · {c['room_id']}" + (" · online" if c["online"] else "")
            results.append(
                {"id": c["id"], "label": c["name"], "sub": sub, "href": f"#/characters/{c['id']}"}
            )
        groups.append(
            {
                "kind": "characters",
                "label": "Characters",
                "total": chars["total"],
                "results": results,
            }
        )
        accounts = await player_accounts.search_accounts(server, q=needle, limit=limit)
        results = []
        for a in accounts["rows"]:
            sub = f"{a['character_count']} characters" + (
                " · suspended" if a["suspended_at"] else ""
            )
            results.append(
                {"id": a["id"], "label": a["username"], "sub": sub, "href": f"#/accounts/{a['id']}"}
            )
        groups.append(
            {
                "kind": "accounts",
                "label": "Accounts",
                "total": accounts["total"],
                "results": results,
            }
        )
    groups += await asyncio.to_thread(
        _content_groups,
        needle,
        limit,
        ctx.may_use_tool("world") or ctx.may_use_tool("content"),
        ctx.may_use_tool("items"),
        ctx.may_use_tool("entities"),
    )
    if ctx.may_use_tool("lexicon") and getattr(server, "lexicon", None) is not None:
        hits = []
        for key in sorted(server.lexicon.keys()):
            value = server.lexicon.get(key)
            if _match(needle, key, value):
                sub = str(value or "")[:80]
                hits.append({"id": key, "label": key, "sub": sub, "href": f"#/lexicon/{key}"})
        groups.append(_group("lexicon", "Lexicon", hits, limit))
    return {"q": q, "groups": [g for g in groups if g["total"]]}
