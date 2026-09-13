"""Admin routes for NPC shops — stock, owners, wallets, and the sales ledger."""

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends

from fablestar.admin.admin_security import AdminContext
from fablestar.admin.route_helpers import require_tool

if TYPE_CHECKING:
    from fablestar.server import FablestarServer

logger = logging.getLogger(__name__)

ZONES_DIR = Path("content") / "world" / "zones"


def _all_room_ids() -> list[str]:
    out = []
    if ZONES_DIR.exists():
        for zdir in sorted(ZONES_DIR.iterdir()):
            rooms = zdir / "rooms"
            if rooms.is_dir():
                out.extend(f"{zdir.name}:{f.stem}" for f in sorted(rooms.glob("*.yaml")))
    return out


def build_shops_router(server: "FablestarServer") -> APIRouter:
    router = APIRouter()

    @router.get("/admin/shops")
    async def shops_list(
        _ctx: Annotated[AdminContext, Depends(require_tool("shops"))],
    ):
        rows = []
        agent_manager = getattr(server, "agent_manager", None)
        agents_by_id = agent_manager.agents if agent_manager else {}
        for room_id in _all_room_ids():
            room = server.content_loader.get_room(room_id)
            if room is None or room.shop is None:
                continue
            shop = room.shop

            # Ledger tail + running totals
            ledger = []
            sold_count = revenue = bought_count = spend = 0
            try:
                raw = await server.redis.client.lrange(f"shopledger:{room_id}", 0, 199)
                for item in raw or []:
                    try:
                        e = json.loads(item if isinstance(item, str) else item.decode())
                    except Exception:
                        continue
                    ledger.append(e)
                    if e.get("kind") == "sale":
                        sold_count += 1
                        revenue += int(e.get("price", 0))
                    elif e.get("kind") == "purchase":
                        bought_count += 1
                        spend += int(e.get("price", 0))
            except Exception:
                logger.debug("shop ledger read failed for %s", room_id, exc_info=True)

            # Owner details (live agent wallet/location/inventory)
            owner = None
            if shop.owner and shop.owner in agents_by_id:
                state = agents_by_id[shop.owner]
                name = state.persona.name
                stats = await server.redis.get_player_stats(name)
                inventory = await server.redis.get_player_inventory(name)
                owner = {
                    "id": shop.owner,
                    "name": name,
                    "digi": int(stats.get("digi", 0) or 0),
                    "room_id": await server.redis.get_player_location(name),
                    "home_room": stats.get("home_room"),
                    "inventory": [it.get("name", "?") for it in inventory],
                }
            elif shop.owner:
                owner = {"id": shop.owner, "name": shop.owner, "digi": None, "room_id": None}

            stock = []
            for entry in shop.sells:
                tmpl = server.content_loader.get_item_template(entry.template)
                stock.append(
                    {
                        "template": entry.template,
                        "name": tmpl.name if tmpl else entry.template,
                        "price": entry.price,
                    }
                )
            rows.append(
                {
                    "room_id": room_id,
                    "shop_name": shop.name,
                    "owner": owner,
                    "stock": stock,
                    "buys": shop.buys,
                    "buy_rate": shop.buy_rate,
                    "sold_count": sold_count,
                    "revenue": revenue,
                    "bought_count": bought_count,
                    "spend": spend,
                    "ledger": ledger[:30],
                }
            )
        return rows

    return router
