"""Money in the world: each currency's total across saved characters, and who holds the most.

Balances are read from the saved character rows, which the server updates about once a minute, so
the totals can trail live play by that much. The wallet stores each currency as a top-level key of
the stats blob, so the database sums them without loading every character.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import BigInteger, func, select

TOP_HOLDERS = 10


async def money_overview(server: Any) -> dict[str, Any]:
    from sage import lexicon
    from sage.state.models import Character

    currencies = []
    async with server.db.session_factory() as session:
        characters = int(await session.scalar(select(func.count()).select_from(Character)) or 0)
        for currency in getattr(server.world, "currencies", None) or []:
            balance = func.coalesce(Character.stats[currency.key].astext.cast(BigInteger), 0)
            total, holders = (
                await session.execute(
                    select(func.coalesce(func.sum(balance), 0), func.count().filter(balance > 0))
                )
            ).one()
            top = (
                await session.execute(
                    select(Character.id, Character.name, balance.label("amount"))
                    .where(balance > 0)
                    .order_by(balance.desc(), Character.name)
                    .limit(TOP_HOLDERS)
                )
            ).all()
            currencies.append(
                {
                    "key": currency.key,
                    "name": lexicon.t(currency.label),
                    "total": int(total),
                    "holders": int(holders),
                    "average": round(int(total) / characters, 1) if characters else 0,
                    "top": [
                        {
                            "id": cid,
                            "name": name,
                            "amount": int(amount),
                            "href": f"#/characters/{cid}",
                        }
                        for cid, name, amount in top
                    ],
                }
            )
    return {"characters": characters, "currencies": currencies}
