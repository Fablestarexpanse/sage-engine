"""PlayerService — /play account auth and character CRUD (login, register, create, delete)."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import TYPE_CHECKING, Any

import bcrypt
from sqlalchemy import func, select

from sage.comfyui_client import generate_portrait_png
from sage.core.config import resolve_workflow_path
from sage.services._shared import (
    authenticate_account,
    resolve_play_account,
    save_portrait_png,
)
from sage.services.play_tokens import issue_play_token
from sage.state.models import Account, Character

if TYPE_CHECKING:
    from sage.server import SageServer

logger = logging.getLogger(__name__)

CHAR_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9 _-]{0,48}[a-zA-Z0-9]$")
MIN_PASSWORD_LENGTH = 8

# Names that would read as staff, as the parser, or as a direction in chat.
RESERVED_CHAR_NAMES = frozenset(
    {
        "admin",
        "administrator",
        "staff",
        "gm",
        "moderator",
        "mod",
        "system",
        "server",
        "nexus",
        "god",
        "nobody",
        "someone",
        "anyone",
        "everyone",
        "self",
        "me",
        "you",
        "north",
        "south",
        "east",
        "west",
        "up",
        "down",
        "northeast",
        "northwest",
        "southeast",
        "southwest",
    }
)


def reserved_name_reason(name: str, claimed_names: set[str]) -> str | None:
    """Why a character name can't be used, or None. Compares case-insensitively."""
    from sage.commands.registry import registry

    key = " ".join(name.split()).lower()
    if key in claimed_names:
        return "character_name_taken"
    if key in RESERVED_CHAR_NAMES or registry.get(key) is not None:
        return "character_name_reserved"
    if any(
        part in RESERVED_CHAR_NAMES - {"up", "down", "me", "you", "self"} for part in key.split()
    ):
        return "character_name_reserved"
    return None


MAX_CHARACTERS_PER_ACCOUNT = 8


def _default_character_portrait_prompt(character_name: str) -> str:
    n = (character_name or "").strip() or "traveler"
    return (
        f"square portrait, full character centered, transparent background, science fiction RPG character {n}, "
        "detailed face and eyes, cinematic soft light, high detail"
    )


class PlayerService:
    """Account credentials and character lifecycle for the web player."""

    def __init__(self, server: SageServer):
        self.server = server

    def _claimed_names(self) -> set[str]:
        """Names plugins claim (automated characters), lowercased."""
        names: set[str] = set()
        for _owner, claim in getattr(getattr(self.server, "plugins", None), "name_claims", []):
            try:
                names |= {n.lower() for n in claim()}
            except Exception:
                logger.debug("name claim by %s failed", _owner, exc_info=True)
        return names

    # ------------------------------------------------------------------
    # Shared response building
    # ------------------------------------------------------------------

    async def character_play_dict(self, character: Character) -> dict[str, Any]:
        from sage.world.progression import PREPARE

        stats = self.server.resolvers.get(PREPARE)(dict(character.stats or {}))
        contributors = getattr(self.server, "snapshot_contributors", None)
        sections = await contributors.build(character.name, stats) if contributors else {}
        return {
            "id": character.id,
            "name": character.name,
            "room_id": character.room_id,
            "portrait_url": character.portrait_url,
            "portrait_prompt": character.portrait_prompt,
            "last_scene_image_url": character.last_scene_image_url,
            "pvp_enabled": bool(character.pvp_enabled),
            "stats": stats,
            "sections": sections,
        }

    async def account_characters_response(self, db_session, account: Account) -> dict[str, Any]:
        """Standard /play auth response: account fields + full character list + economy fields."""
        result = await db_session.execute(
            select(Character).where(Character.account_id == account.id).order_by(Character.id)
        )
        chars_payload = [await self.character_play_dict(c) for c in result.scalars().all()]
        return {
            "ok": True,
            "username": account.username,
            "account_id": account.id,
            "characters": chars_payload,
            "ai_credits": int(account.ai_credits),
            "is_gm": bool(account.is_gm),
            **self.server.economy.public_fields(),
        }

    # ------------------------------------------------------------------
    # Auth endpoints
    # ------------------------------------------------------------------

    async def login(
        self, username: str, password: str, address: str | None = None
    ) -> dict[str, Any]:
        """REST: validate credentials, list characters, and issue a play session token."""
        from sage.services import moderation

        username = (username or "").strip()
        if not username:
            return {"ok": False, "error": "username_required"}
        if await moderation.active_ban(self.server, address):
            return {"ok": False, "error": "address_banned"}
        async with self.server.db.session_factory() as db_session:
            account = await authenticate_account(db_session, username, password)
            if account is None:
                return {"ok": False, "error": "invalid_credentials"}
            if account.suspended_at is not None:
                return {"ok": False, "error": "account_suspended"}
            account.last_login = datetime.utcnow()
            response = await self.account_characters_response(db_session, account)
            response["play_token"] = issue_play_token(self.server, account.id)
            account_id = account.id
            await db_session.commit()
        await moderation.record_login(self.server, account_id, "password", address)
        return response

    async def register(
        self, username: str, password: str, address: str | None = None
    ) -> dict[str, Any]:
        """REST: create account (characters are added via character creation UI)."""
        from sage.services import moderation

        if not moderation.settings(self.server).registration_open:
            return {"ok": False, "error": "registration_closed"}
        if await moderation.active_ban(self.server, address):
            return {"ok": False, "error": "address_banned"}
        username = (username or "").strip()
        if len(username) < 2:
            return {"ok": False, "error": "username_too_short"}
        if len(username) > 50:
            return {"ok": False, "error": "username_too_long"}
        if len(password) < MIN_PASSWORD_LENGTH:
            return {"ok": False, "error": "password_too_short"}
        async with self.server.db.session_factory() as db_session:
            result = await db_session.execute(select(Account).where(Account.username == username))
            if result.scalar_one_or_none():
                return {"ok": False, "error": "username_taken"}
            pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
            start_credits = int(self.server.config.comfyui.starting_ai_credits)
            account = Account(
                username=username,
                password_hash=pw_hash,
                last_login=datetime.utcnow(),
                ai_credits=start_credits,
            )
            db_session.add(account)
            await db_session.commit()
            await db_session.refresh(account)
            aid = account.id
            ec = account.ai_credits
            is_gm = bool(account.is_gm)
        return {
            "ok": True,
            "username": username,
            "account_id": aid,
            "characters": [],
            "ai_credits": ec,
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
        if not CHAR_NAME_RE.match(name) or "  " in name:
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

    def _clean_chargen(
        self, chargen: dict[str, Any] | None
    ) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        """World-defined creation choices through chargen.validate. Returns (error_response, cleaned)."""
        from sage.world.chargen import VALIDATE

        error, cleaned = self.server.resolvers.get(VALIDATE)(dict(chargen or {}))
        if error:
            return {"ok": False, "error": error}, {}
        return None, cleaned

    async def _generate_create_portrait(
        self, account_id: int, name: str, pp: str | None
    ) -> tuple[dict[str, Any] | None, str | None, str | None, str | None, int]:
        """ComfyUI portrait for character create (debit → generate → write → refund on failure).

        Returns (error_response, portrait_url, portrait_prompt, gen_failed_detail, charged).
        """
        cfg = self.server.config.comfyui
        if not (cfg.enabled and resolve_workflow_path(cfg, "portrait").is_file()):
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

    async def _insert_character(
        self,
        db_session,
        account_id: int,
        name: str,
        portrait_url: str | None,
        portrait_prompt: str | None,
        chargen_clean: dict[str, Any] | None,
    ) -> Character:
        """Insert a fresh character row with initialised stats (caller validated the name)."""
        from sage.world.chargen import SEED
        from sage.world.progression import PREPARE, SEED_ATTRIBUTES

        character = Character(
            account_id=account_id,
            name=name,
            room_id=self.server.world.start_room,
            portrait_url=portrait_url,
            portrait_prompt=portrait_prompt,
            pvp_enabled=False,
        )
        db_session.add(character)
        await db_session.commit()
        await db_session.refresh(character)
        merged_stats = self.server.resolvers.get(PREPARE)(dict(character.stats or {}))
        # The world's stat schema first (attribute defaults, full vitals), then creation choices.
        world = self.server.world
        self.server.resolvers.get(SEED_ATTRIBUTES)(merged_stats, world.attribute_defaults())
        world.seed_vitals(merged_stats)
        self.server.resolvers.get(SEED)(merged_stats, dict(chargen_clean or {}))
        if self.server.wallet.enabled:
            self.server.wallet.set(merged_stats, self.server.wallet.starting())
        character.stats = merged_stats
        await db_session.commit()
        await db_session.refresh(character)
        return character

    async def create_character(
        self,
        username: str,
        password: str,
        name: str,
        portrait_prompt: str = "",
        portrait_url: str = "",
        chargen: dict[str, Any] | None = None,
        *,
        token: str = "",
    ) -> dict[str, Any]:
        username = (username or "").strip()
        name = (name or "").strip()
        if not username and not token:
            return {"ok": False, "error": "username_required"}
        err, p_url, pp = self._validate_create_character_inputs(name, portrait_url, portrait_prompt)
        if err:
            return err
        err, chargen_clean = self._clean_chargen(chargen)
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

            reason = reserved_name_reason(name, self._claimed_names())
            if reason:
                return {"ok": False, "error": reason}
            taken = await db_session.execute(
                select(Character.id).where(func.lower(Character.name) == name.lower())
            )
            if taken.first() is not None:
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
            character = await self._insert_character(
                db_session, account_id, name, p_url, pp, chargen_clean
            )
            payload = await self.character_play_dict(character)
            result = await db_session.execute(
                select(Character).where(Character.account_id == account_id).order_by(Character.id)
            )
            all_chars = [await self.character_play_dict(c) for c in result.scalars().all()]

        final_bal = await self.server.economy.read_balance(account_id)
        out: dict[str, Any] = {
            "ok": True,
            "character": payload,
            "characters": all_chars,
            **self.server.economy.public_fields(),
            "ai_credits": final_bal,
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
