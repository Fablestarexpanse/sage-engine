"""EconomyService — echo-credit balance, generation debits/refunds, public economy fields."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from fablestar.state.models import Account

if TYPE_CHECKING:
    from fablestar.server import FablestarServer


class EconomyService:
    """Owns the spendable echo-credit balance (AI art currency) on player accounts.

    Reads config through the server so live settings updates (which replace the
    config object) are always observed.
    """

    def __init__(self, server: FablestarServer):
        self.server = server

    def public_fields(self) -> dict[str, Any]:
        c = self.server.config.comfyui
        s = self.server.config.server
        return {
            "currency_display_name": c.currency_display_name,
            "game_currency_display_name": s.game_currency_display_name,
            "pixels_per_usd": int(c.pixels_per_usd),
        }

    async def read_balance(self, account_id: int) -> int:
        async with self.server.db.session_factory() as db_session:
            result = await db_session.execute(
                select(Account.echo_credits).where(Account.id == account_id)
            )
            v = result.scalar_one_or_none()
            return int(v) if v is not None else 0

    async def debit_for_generation(
        self, account_id: int, cost: int
    ) -> tuple[bool, dict[str, Any], int, int]:
        """
        Debit echo_credits before ComfyUI. Returns:
        (success, error_response_dict_if_failed, balance_after, amount_charged).
        When economy is off or cost is 0, amount_charged is 0 and balance_after is current balance.
        """
        c = self.server.config.comfyui
        if not c.economy_enabled or cost <= 0:
            bal = await self.read_balance(account_id)
            return True, {}, bal, 0
        async with self.server.db.session_factory() as db_session:
            result = await db_session.execute(
                select(Account).where(Account.id == account_id).with_for_update()
            )
            account = result.scalar_one_or_none()
            if account is None:
                return False, {"ok": False, "error": "account_not_found"}, 0, 0
            bal = int(account.echo_credits)
            if bal < cost:
                err = {
                    "ok": False,
                    "error": "insufficient_credits",
                    "balance": bal,
                    "required": cost,
                    **self.public_fields(),
                }
                await db_session.rollback()
                return False, err, bal, 0
            account.echo_credits = bal - cost
            await db_session.commit()
            return True, {}, bal - cost, cost

    async def refund(self, account_id: int, amount: int) -> None:
        if amount <= 0 or not self.server.config.comfyui.economy_enabled:
            return
        async with self.server.db.session_factory() as db_session:
            result = await db_session.execute(
                select(Account).where(Account.id == account_id).with_for_update()
            )
            account = result.scalar_one_or_none()
            if account is None:
                await db_session.rollback()
                return
            account.echo_credits = int(account.echo_credits) + amount
            await db_session.commit()
