"""PlayerService — /play account auth and character CRUD (login, register, create, delete)."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import TYPE_CHECKING, Any

import bcrypt
from sqlalchemy import select

from fablestar.comfyui_client import generate_portrait_png
from fablestar.core.config import resolve_config_asset_path
from fablestar.services._shared import (
    authenticate_account,
    resolve_play_account,
    save_portrait_png,
)
from fablestar.services.play_tokens import issue_play_token
from fablestar.state.models import Account, Character

if TYPE_CHECKING:
    from fablestar.server import FablestarServer

logger = logging.getLogger(__name__)

CHAR_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9 _-]{1,49}$")
MAX_CHARACTERS_PER_ACCOUNT = 8


def _default_character_portrait_prompt(character_name: str) -> str:
    n = (character_name or "").strip() or "traveler"
    return (
        f"square portrait, full character centered, transparent background, science fiction RPG character {n}, "
        "detailed face and eyes, cinematic soft light, high detail"
    )


class PlayerService:
    """Account credentials and character lifecycle for the web player."""

    def __init__(self, server: FablestarServer):
        self.server = server

    # ------------------------------------------------------------------
    # Shared response building
    # ------------------------------------------------------------------

    def character_play_dict(self, character: Character) -> dict[str, Any]:
        from fablestar.proficiencies.state_helpers import (
            ensure_proficiency_block,
            migrate_legacy_stats,
            total_proficiency_levels,
        )

        stats = migrate_legacy_stats(dict(character.stats or {}))
        ensure_proficiency_block(stats)
        try:
            reg = self.server.content_loader.get_proficiency_registry()
            total_lv = total_proficiency_levels(stats, registry=reg)
        except Exception:
            total_lv = total_proficiency_levels(stats)
        return {
            "id": character.id,
            "name": character.name,
            "room_id": character.room_id,
            "portrait_url": character.portrait_url,
            "portrait_prompt": character.portrait_prompt,
            "last_scene_image_url": character.last_scene_image_url,
            "digi_balance": int(character.digi_balance),
            "pvp_enabled": bool(character.pvp_enabled),
            "reputation": int(character.reputation),
            "stats": stats,
            "resonance_levels_total": total_lv,
        }

    async def account_characters_response(self, db_session, account: Account) -> dict[str, Any]:
        """Standard /play auth response: account fields + full character list + economy fields."""
        result = await db_session.execute(
            select(Character).where(Character.account_id == account.id).order_by(Character.id)
        )
        chars_payload = [self.character_play_dict(c) for c in result.scalars().all()]
        return {
            "ok": True,
            "username": account.username,
            "account_id": account.id,
            "characters": chars_payload,
            "echo_credits": int(account.echo_credits),
            "is_gm": bool(account.is_gm),
            **self.server.economy.public_fields(),
        }

    # ------------------------------------------------------------------
    # Auth endpoints
    # ------------------------------------------------------------------

    async def login(self, username: str, password: str) -> dict[str, Any]:
        """REST: validate credentials, list characters, and issue a play session token."""
        username = (username or "").strip()
        if not username:
            return {"ok": False, "error": "username_required"}
        async with self.server.db.session_factory() as db_session:
            account = await authenticate_account(db_session, username, password)
            if account is None:
                return {"ok": False, "error": "invalid_credentials"}
            account.last_login = datetime.utcnow()
            response = await self.account_characters_response(db_session, account)
            response["play_token"] = issue_play_token(self.server, account.id)
            await db_session.commit()
        return response

    async def register(self, username: str, password: str) -> dict[str, Any]:
        """REST: create account (characters are added via character creation UI)."""
        username = (username or "").strip()
        if len(username) < 2:
            return {"ok": False, "error": "username_too_short"}
        if len(password) < 4:
            return {"ok": False, "error": "password_too_short"}
        async with self.server.db.session_factory() as db_session:
            result = await db_session.execute(select(Account).where(Account.username == username))
            if result.scalar_one_or_none():
                return {"ok": False, "error": "username_taken"}
            pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
            start_credits = int(self.server.config.comfyui.starting_echo_credits)
            account = Account(
                username=username,
                password_hash=pw_hash,
                last_login=datetime.utcnow(),
                echo_credits=start_credits,
            )
            db_session.add(account)
            await db_session.commit()
            await db_session.refresh(account)
            aid = account.id
            ec = account.echo_credits
            is_gm = bool(account.is_gm)
        return {
            "ok": True,
            "username": username,
            "account_id": aid,
            "characters": [],
            "echo_credits": ec,
            "is_gm": is_gm,
            "play_token": issue_play_token(self.server, aid),
            **self.server.economy.public_fields(),
        }

    async def refresh_characters(
        self, username: str, password: str, *, token: str = ""
    ) -> dict[str, Any]:
        """Re-list characters after create (same shape as login)."""
        username = (username or "").strip()
        if not username and not token:
            return {"ok": False, "error": "username_required"}
        async with self.server.db.session_factory() as db_session:
            account = await resolve_play_account(
                db_session, self.server, token=token, username=username, password=password
            )
            if account is None:
                return {"ok": False, "error": "invalid_credentials"}
            return await self.account_characters_response(db_session, account)

    # ------------------------------------------------------------------
    # Character creation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_create_character_inputs(
        name: str, portrait_url: str, portrait_prompt: str
    ) -> tuple[dict[str, Any] | None, str | None, str | None]:
        """Pure validation. Returns (error_response, portrait_url, portrait_prompt)."""
        if not CHAR_NAME_RE.match(name):
            return {"ok": False, "error": "invalid_character_name"}, None, None
        p_url = (portrait_url or "").strip() or None
        if p_url and (
            not p_url.startswith("/media/portraits/") or ".." in p_url or len(p_url) > 2048
        ):
            return {"ok": False, "error": "invalid_portrait_url"}, None, None
        pp = (portrait_prompt or "").strip() or None
        if pp and len(pp) > 4000:
            return {"ok": False, "error": "portrait_prompt_too_long"}, None, None
        return None, p_url, pp

    def _clean_starter_proficiencies(
        self, starter_proficiencies: dict[str, int] | None
    ) -> tuple[dict[str, Any] | None, dict[str, int]]:
        """Coerce and validate the chargen skill allocation. Returns (error_response, cleaned)."""
        starter_clean: dict[str, int] = {}
        if starter_proficiencies:
            for k, v in starter_proficiencies.items():
                if not isinstance(k, str):
                    continue
                kid = k.strip()
                if not kid:
                    continue
                try:
                    n = int(v)
                except (TypeError, ValueError):
                    return {"ok": False, "error": "invalid_starter_proficiencies"}, {}
                if n != 0:
                    starter_clean[kid] = n
        if starter_clean:
            from fablestar.proficiencies.starter import validate_starter_allocation

            reg0 = self.server.content_loader.get_proficiency_registry()
            ok_st, err_st = validate_starter_allocation(starter_clean, reg0)
            if not ok_st:
                return {"ok": False, "error": err_st}, {}
        return None, starter_clean

    async def _generate_create_portrait(
        self, account_id: int, name: str, pp: str | None
    ) -> tuple[dict[str, Any] | None, str | None, str | None, str | None, int]:
        """ComfyUI portrait for character create (debit → generate → write → refund on failure).

        Returns (error_response, portrait_url, portrait_prompt, gen_failed_detail, charged).
        """
        cfg = self.server.config.comfyui
        if not (cfg.enabled and resolve_config_asset_path(cfg.workflow_path).is_file()):
            return None, None, pp, None, 0
        prompt_use = pp if pp else _default_character_portrait_prompt(name)
        cost_c = int(cfg.character_create_portrait_cost)
        ok_d, err_d, _bal_d, charged = await self.server.economy.debit_for_generation(
            account_id, cost_c
        )
        if not ok_d:
            return err_d, None, pp, None, 0
        try:
            png, _ = await generate_portrait_png(cfg, prompt_use)
            return None, save_portrait_png(png), pp or prompt_use, None, charged
        except Exception as e:
            if charged:
                await self.server.economy.refund(account_id, charged)
            logger.warning("ComfyUI portrait on character create failed: %s", e, exc_info=True)
            return None, None, pp, str(e), charged

    async def create_character(
        self,
        username: str,
        password: str,
        name: str,
        portrait_prompt: str = "",
        portrait_url: str = "",
        starter_proficiencies: dict[str, int] | None = None,
        token: str = "",
    ) -> dict[str, Any]:
        username = (username or "").strip()
        name = (name or "").strip()
        if not username and not token:
            return {"ok": False, "error": "username_required"}
        err, p_url, pp = self._validate_create_character_inputs(name, portrait_url, portrait_prompt)
        if err:
            return err
        err, starter_clean = self._clean_starter_proficiencies(starter_proficiencies)
        if err:
            return err

        async with self.server.db.session_factory() as db_session:
            account = await resolve_play_account(
                db_session, self.server, token=token, username=username, password=password
            )
            if account is None:
                return {"ok": False, "error": "invalid_credentials"}
            account_id = account.id
            is_gm = bool(account.is_gm)

            result = await db_session.execute(
                select(Character).where(Character.account_id == account.id)
            )
            if len(list(result.scalars().all())) >= MAX_CHARACTERS_PER_ACCOUNT:
                return {"ok": False, "error": "character_limit"}

            taken = await db_session.execute(select(Character).where(Character.name == name))
            if taken.scalar_one_or_none():
                return {"ok": False, "error": "character_name_taken"}

        portrait_gen_failed: str | None = None
        create_portrait_charged = 0
        if not p_url:
            (
                err,
                p_url,
                pp,
                portrait_gen_failed,
                create_portrait_charged,
            ) = await self._generate_create_portrait(account_id, name, pp)
            if err:
                return err

        async with self.server.db.session_factory() as db_session:
            start_digi = int(self.server.config.server.starting_digi_balance)
            character = Character(
                account_id=account_id,
                name=name,
                room_id="starter_zone:entrance",
                portrait_url=p_url,
                portrait_prompt=pp,
                digi_balance=start_digi,
                pvp_enabled=False,
                reputation=0,
            )
            db_session.add(character)
            await db_session.commit()
            await db_session.refresh(character)
            from fablestar.proficiencies.starter import apply_starter_to_stats
            from fablestar.proficiencies.state_helpers import (
                ensure_proficiency_block,
                migrate_legacy_stats,
            )

            merged_stats = migrate_legacy_stats(dict(character.stats or {}))
            ensure_proficiency_block(merged_stats)
            if starter_clean:
                apply_starter_to_stats(
                    merged_stats,
                    starter_clean,
                    self.server.content_loader.get_proficiency_registry(),
                )
            character.stats = merged_stats
            await db_session.commit()
            await db_session.refresh(character)
            payload = self.character_play_dict(character)
            result = await db_session.execute(
                select(Character).where(Character.account_id == account_id).order_by(Character.id)
            )
            all_chars = [self.character_play_dict(c) for c in result.scalars().all()]

        final_bal = await self.server.economy.read_balance(account_id)
        out: dict[str, Any] = {
            "ok": True,
            "character": payload,
            "characters": all_chars,
            **self.server.economy.public_fields(),
            "echo_credits": final_bal,
            "is_gm": is_gm,
        }
        if create_portrait_charged and not portrait_gen_failed:
            out["cost_charged"] = create_portrait_charged
        if portrait_gen_failed:
            out["portrait_generation_failed"] = True
            out["portrait_generation_detail"] = portrait_gen_failed
        return out

    async def delete_character(
        self, username: str, password: str, character_id: int, *, token: str = ""
    ) -> dict[str, Any]:
        """Remove one character if it belongs to the authenticated account."""
        username = (username or "").strip()
        if not username and not token:
            return {"ok": False, "error": "username_required"}
        if character_id is None or character_id < 1:
            return {"ok": False, "error": "character_id_invalid"}
        async with self.server.db.session_factory() as db_session:
            account = await resolve_play_account(
                db_session, self.server, token=token, username=username, password=password
            )
            if account is None:
                return {"ok": False, "error": "invalid_credentials"}
            result = await db_session.execute(select(Character).where(Character.id == character_id))
            char = result.scalar_one_or_none()
            if char is None or char.account_id != account.id:
                return {"ok": False, "error": "character_not_found"}
            await db_session.delete(char)
            await db_session.commit()
            return await self.account_characters_response(db_session, account)
