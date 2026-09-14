"""What points at a room, item or creature: content files that name it, and live state that holds it.

Content references are found generically. Every room, item and creature file is walked, and any
field whose value (or a key inside it) is exactly the record's id counts. So an exit destination,
a spawn entry, a loot drop, or a plugin field such as a shop's stock or a recipe's inputs is found
with no knowledge of which plugin owns the field.
"""

from __future__ import annotations

from typing import Any

from sage.admin import content_browser

MAX_ROWS = 200


def _names(node: Any, target: str) -> bool:
    if isinstance(node, str):
        return node == target
    if isinstance(node, dict):
        return any(k == target or _names(v, target) for k, v in node.items())
    if isinstance(node, list):
        return any(_names(v, target) for v in node)
    return False


def content_references(target: str) -> list[dict[str, Any]]:
    """Content records with a field naming ``target``: one row per (record, top-level field)."""
    sources: list[tuple[str, str, str, dict[str, Any]]] = []
    for zone, slug, data, error in content_browser.room_files():
        if error is None:
            room_id = str(data.get("id") or f"{zone}:{slug}")
            sources.append(("room", room_id, f"#/content/rooms/{zone}/{slug}", data))
    for kind, label, tab in (("items", "item", "items"), ("entities", "creature", "creatures")):
        for path, data, error in content_browser.template_files(kind):
            if error is None:
                tid = str(data.get("id", path.stem))
                sources.append((label, tid, f"#/content/{tab}/{tid}", data))
    rows: list[dict[str, Any]] = []
    for kind, record_id, href, data in sources:
        if record_id == target:  # the record's own file
            continue
        for field, value in data.items():
            if field == "id" or not _names(value, target):
                continue
            rows.append(
                {
                    "kind": kind,
                    "id": record_id,
                    "name": str(data.get("name") or record_id),
                    "field": field,
                    "href": href,
                }
            )
    return rows


async def live_references(server: Any, kind: str, target: str) -> dict[str, Any]:
    """Saved and live state holding the record: carriers, floor copies, live creatures, occupants."""
    from sqlalchemy import func, select

    from sage.state.models import Character

    out: dict[str, Any] = {}
    redis = server.redis
    if kind == "items":
        stmt = select(Character.id, Character.name).where(
            Character.inventory.contains([{"template": target}])
        )
        async with server.db.session_factory() as session:
            total = await session.scalar(select(func.count()).select_from(stmt.subquery()))
            carriers = (await session.execute(stmt.order_by(Character.name).limit(MAX_ROWS))).all()
        out["carried_by"] = {
            "total": int(total or 0),
            "rows": [
                {"id": cid, "name": name, "href": f"#/characters/{cid}"} for cid, name in carriers
            ],
        }
        floor: dict[str, int] = {}
        for room_id, item_ids in (await redis.scan_sets("room_items")).items():
            for item_id in item_ids:
                state = await redis.get_item_state(item_id) or {}
                if state.get("template") == target:
                    floor[room_id] = floor.get(room_id, 0) + 1
        out["on_floors"] = [{"room_id": r, "count": n} for r, n in sorted(floor.items())]
    elif kind == "entities":
        states, _ = await redis.scan_states("entity_state", 100_000)
        rooms: dict[str, int] = {}
        for state in states:
            if state.get("template") == target:
                room = str(state.get("room_id") or "?")
                rooms[room] = rooms.get(room, 0) + 1
        out["alive"] = [{"room_id": r, "count": n} for r, n in sorted(rooms.items())]
    elif kind == "rooms":
        stmt = select(Character.id, Character.name).where(Character.room_id == target)
        async with server.db.session_factory() as session:
            total = await session.scalar(select(func.count()).select_from(stmt.subquery()))
            saved = (await session.execute(stmt.order_by(Character.name).limit(MAX_ROWS))).all()
        out["saved_here"] = {
            "total": int(total or 0),
            "rows": [
                {"id": cid, "name": name, "href": f"#/characters/{cid}"} for cid, name in saved
            ],
        }
        out["present"] = sorted(await redis.get_room_players(target))
    return out
