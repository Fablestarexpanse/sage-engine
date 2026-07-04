"""FablestarServer — owns all subsystems and drives the startup/shutdown lifecycle."""

import asyncio
import json
import logging
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import bcrypt
import httpx
from sqlalchemy import select

from fablestar import app
from fablestar.admin import player_accounts, staff_service
from fablestar.admin.comfyui_persist import save_comfyui_toml
from fablestar.admin.llm_persist import save_llm_toml
from fablestar.admin.nexus import NexusApp
from fablestar.comfyui_client import generate_portrait_png
from fablestar.commands.registry import registry
from fablestar.core.config import (
    ComfyUIConfig,
    Config,
    LLMConfig,
    load_config,
    resolve_config_asset_path,
)
from fablestar.core.tick import TickManager
from fablestar.hot_reload import HotReloader
from fablestar.llm.client import LLMClient
from fablestar.llm.prompts import PromptManager
from fablestar.network.session import Session, SessionManager
from fablestar.parser.dispatcher import CommandDispatcher
from fablestar.state.models import Account, AccountSceneImage, Character
from fablestar.state.persistence import PersistenceManager
from fablestar.state.postgres import PostgresState
from fablestar.state.redis_client import RedisState
from fablestar.world.loader import ContentLoader
from fablestar.world.spawner import EntitySpawnManager

logger = logging.getLogger(__name__)


def _default_character_portrait_prompt(character_name: str) -> str:
    n = (character_name or "").strip() or "traveler"
    return (
        f"square portrait, full character centered, transparent background, science fiction RPG character {n}, "
        "detailed face and eyes, cinematic soft light, high detail"
    )


MAX_CHARACTERS_PER_ACCOUNT = 8


async def _ping_comfyui_http(base_url: str) -> tuple[bool, str]:
    """Return (reachable, error_message). Tries /system_stats then /queue (ComfyUI versions differ)."""
    base = (base_url or "").strip().rstrip("/")
    if not base:
        return False, "empty base_url"
    timeout = httpx.Timeout(4.0, connect=3.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.get(f"{base}/system_stats")
            if r.status_code == 200:
                return True, ""
            if r.status_code == 404:
                r2 = await client.get(f"{base}/queue")
                if r2.status_code == 200:
                    return True, ""
                return False, f"ComfyUI /queue HTTP {r2.status_code}"
            return False, f"ComfyUI /system_stats HTTP {r.status_code}"
    except httpx.ConnectError as e:
        return False, f"cannot connect (is ComfyUI running?): {e}"
    except httpx.TimeoutException:
        return False, "connection timed out"
    except Exception as e:
        return False, str(e)[:400]


def _workflow_has_checkpoint_simple_node(workflow_path: Path) -> bool:
    """True if API workflow JSON includes CheckpointLoaderSimple (needs comfyui.toml checkpoint_name)."""
    if not workflow_path.is_file():
        return False
    try:
        data = json.loads(workflow_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    for v in data.values():
        if isinstance(v, dict) and v.get("class_type") == "CheckpointLoaderSimple":
            return True
    return False


CHAR_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9 _-]{1,49}$")


def _safe_player_scene_storage_url(url: str | None) -> bool:
    """Only allow persisting Nexus-served paths we write under data/ or bundled room-art."""
    u = (url or "").strip()
    if not u.startswith("/media/") or ".." in u or len(u) > 2048:
        return False
    return u.startswith("/media/rooms/") or u.startswith("/media/room-art/")


def _character_play_dict(character: Character) -> dict[str, Any]:
    from fablestar.proficiencies.state_helpers import (
        ensure_proficiency_block,
        migrate_legacy_stats,
        total_proficiency_levels,
    )

    stats = migrate_legacy_stats(dict(character.stats or {}))
    ensure_proficiency_block(stats)
    total_lv = 0
    try:
        inst = getattr(app.app_instance, "content_loader", None)
        if inst is not None:
            reg = inst.get_proficiency_registry()
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


@dataclass
class _CharSnapshot:
    """Plain snapshot of ORM Character data usable after the SQLAlchemy session closes."""

    name: str
    room_id: str
    stats: dict[str, Any]
    inventory: list[Any]


def _snapshot_from_orm(character: Any) -> _CharSnapshot:
    return _CharSnapshot(
        name=character.name,
        room_id=character.room_id,
        stats=dict(character.stats or {}),
        inventory=list(character.inventory or []),
    )


class FablestarServer:
    """
    Main orchestration class for the Fablestar MUD Platform.
    Ties together core systems and manages the server lifecycle.
    """

    def __init__(self, config: Config | None = None):
        self.config = config or load_config()
        self.tick_manager = TickManager(tick_rate=self.config.server.tick_rate)
        self.session_manager = SessionManager()
        self.redis = RedisState(self.config.redis)
        self.db = PostgresState(self.config.database)
        self.persistence = PersistenceManager(self)
        self.content_loader = ContentLoader()
        self.spawner = EntitySpawnManager(self)
        self.hot_reloader = HotReloader(self._on_file_changed)
        self.dispatcher = CommandDispatcher()
        self.nexus = NexusApp(self)

        # LLM Subsystems
        self.llm_client = LLMClient(self.config.llm)
        self.prompt_manager = PromptManager()

        # Internal state
        self._nexus_task: asyncio.Task | None = None
        self._tick_task: asyncio.Task | None = None
        # ISO8601 UTC timestamp of last POST /content/cache/reload (for admin UI)
        self.last_content_reload_at: str | None = None

    def _economy_public_fields(self) -> dict[str, Any]:
        c = self.config.comfyui
        s = self.config.server
        return {
            "currency_display_name": c.currency_display_name,
            "game_currency_display_name": s.game_currency_display_name,
            "pixels_per_usd": int(c.pixels_per_usd),
        }

    @staticmethod
    async def _authenticate_account(db_session, username: str, password: str) -> Account | None:
        """Fetch the account by username and verify the password. None on failure."""
        result = await db_session.execute(select(Account).where(Account.username == username))
        account = result.scalar_one_or_none()
        if not account or not bcrypt.checkpw(password.encode(), account.password_hash.encode()):
            return None
        return account

    async def _account_characters_response(self, db_session, account: Account) -> dict[str, Any]:
        """Standard /play auth response: account fields + full character list + economy fields."""
        result = await db_session.execute(
            select(Character).where(Character.account_id == account.id).order_by(Character.id)
        )
        chars_payload = [_character_play_dict(c) for c in result.scalars().all()]
        return {
            "ok": True,
            "username": account.username,
            "account_id": account.id,
            "characters": chars_payload,
            "echo_credits": int(account.echo_credits),
            "is_gm": bool(account.is_gm),
            **self._economy_public_fields(),
        }

    async def _echo_read_balance(self, account_id: int) -> int:
        async with self.db.session_factory() as db_session:
            result = await db_session.execute(
                select(Account.echo_credits).where(Account.id == account_id)
            )
            v = result.scalar_one_or_none()
            return int(v) if v is not None else 0

    async def _echo_debit_for_generation(
        self, account_id: int, cost: int
    ) -> tuple[bool, dict[str, Any], int, int]:
        """
        Debit echo_credits before ComfyUI. Returns:
        (success, error_response_dict_if_failed, balance_after, amount_charged).
        When economy is off or cost is 0, amount_charged is 0 and balance_after is current balance.
        """
        c = self.config.comfyui
        if not c.economy_enabled or cost <= 0:
            bal = await self._echo_read_balance(account_id)
            return True, {}, bal, 0
        async with self.db.session_factory() as db_session:
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
                    **self._economy_public_fields(),
                }
                await db_session.rollback()
                return False, err, bal, 0
            account.echo_credits = bal - cost
            await db_session.commit()
            return True, {}, bal - cost, cost

    async def _echo_refund(self, account_id: int, amount: int) -> None:
        if amount <= 0 or not self.config.comfyui.economy_enabled:
            return
        async with self.db.session_factory() as db_session:
            result = await db_session.execute(
                select(Account).where(Account.id == account_id).with_for_update()
            )
            account = result.scalar_one_or_none()
            if account is None:
                await db_session.rollback()
                return
            account.echo_credits = int(account.echo_credits) + amount
            await db_session.commit()

    def _staff_role_label(self, role: str) -> str:
        r = (role or "").lower().strip()
        if r == "head_admin":
            return "Head Admin"
        if r == "admin":
            return "Admin"
        if r == "gm":
            return "GM"
        return "Staff"

    async def _notify_play_sessions_json_line(
        self, account_id: int, payload: dict[str, Any]
    ) -> None:
        line = json.dumps(payload, separators=(",", ":"))
        from fablestar.network.session import SessionState

        async with self.db.session_factory() as db_session:
            result = await db_session.execute(
                select(Character.name).where(Character.account_id == account_id)
            )
            names = [row[0] for row in result.all()]
        for name in names:
            sess = self.session_manager.get_session_by_player(name)
            if sess is None or sess.state != SessionState.PLAYING:
                continue
            try:
                await sess.send(line)
            except Exception:
                logger.debug("play client notify failed for player %s", name, exc_info=True)

    async def notify_play_clients_echo_grant(
        self,
        account_id: int,
        *,
        added: int,
        new_balance: int,
    ) -> None:
        """Send a JSON client_notice to any /ws/play session tied to a character on this account."""
        if added <= 0:
            return
        c = self.config.comfyui
        lab = (c.currency_display_name or "pixels").strip() or "pixels"
        payload = {
            "ok": True,
            "client_notice": "echo_credits_granted",
            "echo_credits_added": int(added),
            "echo_credits": int(new_balance),
            "currency_display_name": lab,
            **self._economy_public_fields(),
        }
        await self._notify_play_sessions_json_line(account_id, payload)

    async def notify_play_clients_staff_audit(
        self,
        account_id: int,
        *,
        actor_display_name: str,
        actor_role: str,
        summary_lines: list[str],
        echo_credits: int | None = None,
        echo_credits_added: int | None = None,
        character_name: str | None = None,
        play_account_is_gm: bool | None = None,
    ) -> None:
        """Tell connected play clients who changed their account/character and what changed."""
        if not summary_lines:
            return
        c = self.config.comfyui
        lab = (c.currency_display_name or "pixels").strip() or "pixels"
        payload: dict[str, Any] = {
            "ok": True,
            "client_notice": "staff_account_update",
            "staff_display_name": (actor_display_name or "Staff").strip() or "Staff",
            "staff_role": (actor_role or "gm").strip(),
            "staff_role_label": self._staff_role_label(actor_role),
            "audit_lines": summary_lines,
            "currency_display_name": lab,
            **self._economy_public_fields(),
        }
        if echo_credits is not None:
            payload["echo_credits"] = int(echo_credits)
        if echo_credits_added is not None and echo_credits_added > 0:
            payload["echo_credits_added"] = int(echo_credits_added)
        if character_name:
            payload["character_name"] = character_name
        if play_account_is_gm is not None:
            payload["play_account_is_gm"] = bool(play_account_is_gm)
        await self._notify_play_sessions_json_line(account_id, payload)

    _LLM_PATCH_KEYS = frozenset(
        {
            "primary_backend",
            "lm_studio_url",
            "lm_studio_key",
            "ollama_url",
            "timeout_seconds",
            "chat_model",
            "temperature",
            "cache_ttl",
        }
    )

    def update_llm_settings(self, patch: dict[str, Any], *, persist: bool = True) -> None:
        """Merge LLM fields, rebuild client, optionally write config/llm.toml."""
        data = {k: v for k, v in patch.items() if k in self._LLM_PATCH_KEYS and v is not None}
        if "primary_backend" in data:
            b = str(data["primary_backend"]).lower().strip()
            if b not in ("lm_studio", "ollama"):
                raise ValueError("primary_backend must be 'lm_studio' or 'ollama'")
            data["primary_backend"] = b
        if "timeout_seconds" in data:
            data["timeout_seconds"] = float(data["timeout_seconds"])
        if "temperature" in data:
            data["temperature"] = float(data["temperature"])
        if "cache_ttl" in data:
            data["cache_ttl"] = int(data["cache_ttl"])
        # model_copy(update=...) does not re-run field_validator; merge + validate so
        # lm_studio_url / ollama_url always get /v1 normalization (fixes GET /models on LM Studio).
        merged_llm = {**self.config.llm.model_dump(), **data}
        new_llm = LLMConfig.model_validate(merged_llm)
        self.config = self.config.model_copy(update={"llm": new_llm})
        self.llm_client.reconfigure(self.config.llm)
        if persist:
            save_llm_toml(self.config.llm)

    _COMFYUI_PATCH_KEYS = frozenset(
        {
            "enabled",
            "base_url",
            "workflow_path",
            "positive_prompt_node_id",
            "output_node_id",
            "area_workflow_path",
            "area_positive_prompt_node_id",
            "area_output_node_id",
            "checkpoint_name",
            "timeout_seconds",
            "poll_interval_seconds",
            "economy_enabled",
            "starting_echo_credits",
            "portrait_generation_cost",
            "area_generation_cost",
            "character_create_portrait_cost",
            "currency_display_name",
            "pixels_per_usd",
        }
    )

    def update_comfyui_settings(self, patch: dict[str, Any], *, persist: bool = True) -> None:
        """Merge ComfyUI config fields, optionally write config/comfyui.toml."""
        data = {k: v for k, v in patch.items() if k in self._COMFYUI_PATCH_KEYS and v is not None}
        for int_key in (
            "starting_echo_credits",
            "portrait_generation_cost",
            "area_generation_cost",
            "character_create_portrait_cost",
            "pixels_per_usd",
        ):
            if int_key in data:
                data[int_key] = int(data[int_key])
        for float_key in ("timeout_seconds", "poll_interval_seconds"):
            if float_key in data:
                data[float_key] = float(data[float_key])
        for bool_key in ("enabled", "economy_enabled"):
            if bool_key in data:
                data[bool_key] = bool(data[bool_key])
        merged = {**self.config.comfyui.model_dump(), **data}
        new_cfg = ComfyUIConfig.model_validate(merged)
        self.config = self.config.model_copy(update={"comfyui": new_cfg})
        if persist:
            save_comfyui_toml(self.config.comfyui)

    async def startup(self):
        """Initialize and start all sub-systems."""
        logger.info("Fablestar MUD Platform starting up...")

        # 0. State stores — Redis must be ready before EntitySpawnManager and PersistenceManager
        await self.redis.connect()

        # 0a. Bootstrap dev accounts (requires Redis + Postgres; best-effort)
        try:
            await staff_service.ensure_dev_default_staff(self)
        except Exception as e:
            logger.warning("Default dev staff account not ensured: %s", e)
        try:
            await player_accounts.ensure_dev_default_play_accounts(self)
        except Exception as e:
            logger.warning("Default dev play accounts not ensured: %s", e)

        # 1. Command registry — must complete before NexusApp handles any WebSocket connections
        registry.reload_module("fablestar.commands.info")
        registry.reload_module("fablestar.commands.communication")
        registry.reload_module("fablestar.commands.movement")
        registry.reload_module("fablestar.commands.combat")
        registry.reload_module("fablestar.commands.items")
        registry.reload_module("fablestar.commands.proficiency")
        registry.reload_module("fablestar.commands.admin")

        # 2. Tick handlers — must be registered before the tick loop starts in step 4
        self.tick_manager.register(self.spawner.on_tick)
        self.tick_manager.register(self.persistence.on_tick)

        # 3. HotReloader — watches content/ and commands/; safe to start any time after step 1
        await self.hot_reloader.start(["content", "src/fablestar/commands", "config", "prompts"])

        # 4. NexusApp (FastAPI HTTP + WebSocket) — requires command registry (step 1) to be ready
        self._nexus_task = asyncio.create_task(self.nexus.start())

        # 5. Tick loop — requires tick handlers registered (step 2) and Redis connected (step 0)
        self._tick_task = asyncio.create_task(self.tick_manager.run())

        logger.info("Startup complete. Server is running.")

    async def shutdown(self):
        """Gracefully stop all sub-systems."""
        logger.info("Fablestar MUD Platform shutting down...")

        self.hot_reloader.stop()
        self.tick_manager.stop()
        await self.redis.disconnect()
        await self.db.close()

        for task in (self._tick_task, self._nexus_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        logger.info("Shutdown complete.")

    async def _authenticate_websocket(self, session: Session) -> _CharSnapshot | None:
        """
        WebSocket player: first message must be JSON:
        {"username","password","character_id": optional int}
        Register accounts via POST /play/auth/register; pick a character in the UI when several exist.
        On failure, sends a JSON error line and returns None.
        """
        raw = await session.protocol.receive()
        if raw is None:
            return None
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            await session.send(json.dumps({"ok": False, "error": "invalid_handshake"}) + "\r\n")
            return None
        username = (data.get("username") or "").strip()
        password = data.get("password") or ""
        char_id_raw = data.get("character_id")
        char_id: int | None = None
        if char_id_raw is not None:
            try:
                char_id = int(char_id_raw)
            except (TypeError, ValueError):
                char_id = None
        if not username:
            await session.send(json.dumps({"ok": False, "error": "username_required"}) + "\r\n")
            return None

        async with self.db.session_factory() as db_session:
            account = await self._authenticate_account(db_session, username, password)
            if account is None:
                await session.send(
                    json.dumps({"ok": False, "error": "invalid_credentials"}) + "\r\n"
                )
                return None

            result = await db_session.execute(
                select(Character).where(Character.account_id == account.id).order_by(Character.id)
            )
            characters = list(result.scalars().all())
            character: Character | None = None
            if not characters:
                await session.send(json.dumps({"ok": False, "error": "no_character"}) + "\r\n")
                return None
            if char_id is not None:
                character = next((c for c in characters if c.id == char_id), None)
                if character is None:
                    await session.send(
                        json.dumps({"ok": False, "error": "character_not_found"}) + "\r\n"
                    )
                    return None
            elif len(characters) == 1:
                character = characters[0]
            else:
                await session.send(
                    json.dumps({"ok": False, "error": "character_required"}) + "\r\n"
                )
                return None

            account.last_login = datetime.utcnow()
            await db_session.commit()
            await db_session.refresh(character)

        return _snapshot_from_orm(character)

    async def play_login(self, username: str, password: str) -> dict[str, Any]:
        """REST: validate credentials and list characters for the web UI."""
        username = (username or "").strip()
        if not username:
            return {"ok": False, "error": "username_required"}
        async with self.db.session_factory() as db_session:
            account = await self._authenticate_account(db_session, username, password)
            if account is None:
                return {"ok": False, "error": "invalid_credentials"}
            account.last_login = datetime.utcnow()
            response = await self._account_characters_response(db_session, account)
            await db_session.commit()
        return response

    async def play_register(self, username: str, password: str) -> dict[str, Any]:
        """REST: create account (characters are added via character creation UI)."""
        username = (username or "").strip()
        if len(username) < 2:
            return {"ok": False, "error": "username_too_short"}
        if len(password) < 4:
            return {"ok": False, "error": "password_too_short"}
        async with self.db.session_factory() as db_session:
            result = await db_session.execute(select(Account).where(Account.username == username))
            if result.scalar_one_or_none():
                return {"ok": False, "error": "username_taken"}
            pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
            start_credits = int(self.config.comfyui.starting_echo_credits)
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
        eco = self._economy_public_fields()
        return {
            "ok": True,
            "username": username,
            "account_id": aid,
            "characters": [],
            "echo_credits": ec,
            "is_gm": is_gm,
            **eco,
        }

    async def play_comfyui_status(self) -> dict[str, Any]:
        c = self.config.comfyui
        portrait_resolved = resolve_config_asset_path(c.workflow_path)
        wf = portrait_resolved.is_file()
        ready = bool(c.enabled and wf)
        area_wp = (c.area_workflow_path or "").strip() or c.workflow_path
        area_path = resolve_config_asset_path(area_wp)
        area_wf = area_path.is_file()
        area_ready = bool(c.enabled and area_wf)
        ckpt_set = bool((c.checkpoint_name or "").strip())
        area_uses_ckpt_loader = _workflow_has_checkpoint_simple_node(area_path)
        portrait_uses_ckpt_loader = _workflow_has_checkpoint_simple_node(portrait_resolved)
        suggest_checkpoint_name_in_toml = bool(
            c.enabled and area_wf and area_uses_ckpt_loader and not ckpt_set
        )
        comfy_reachable = False
        comfy_ping_error = ""
        if c.enabled:
            comfy_reachable, comfy_ping_error = await _ping_comfyui_http(c.base_url)
        return {
            "ok": True,
            "enabled": c.enabled,
            "base_url": c.base_url,
            "workflow_path": c.workflow_path,
            "positive_prompt_node_id": c.positive_prompt_node_id,
            "output_node_id": c.output_node_id,
            "workflow_present": wf,
            "ready": ready,
            "portrait_workflow_uses_checkpoint_loader": portrait_uses_ckpt_loader,
            "area_workflow_present": area_wf,
            "area_ready": area_ready,
            "area_workflow_path": area_wp,
            "area_workflow_uses_checkpoint_loader": area_uses_ckpt_loader,
            "checkpoint_name_set": ckpt_set,
            "suggest_checkpoint_name_in_toml": suggest_checkpoint_name_in_toml,
            "comfy_reachable": comfy_reachable,
            "comfy_ping_error": comfy_ping_error,
            "economy_enabled": bool(c.economy_enabled),
            "area_generation_cost": int(c.area_generation_cost),
            "portrait_generation_cost": int(c.portrait_generation_cost),
            "pixels_per_usd": int(c.pixels_per_usd),
            "currency_display_name": (c.currency_display_name or "pixels").strip() or "pixels",
        }

    async def ping_comfyui(self) -> tuple[bool, str]:
        """Return (reachable, error_message) for the configured ComfyUI base URL."""
        return await _ping_comfyui_http(self.config.comfyui.base_url)

    async def forge_suggest_area_image_prompt(
        self,
        room_name: str,
        room_type: str,
        depth: int,
        description_base: str,
    ) -> dict[str, Any]:
        """LM Studio / OpenAI-compatible: short ComfyUI prompt from room fields."""
        prompt = self.prompt_manager.render(
            "forge_area_image_prompt",
            room_name=room_name or "?",
            room_type=room_type or "chamber",
            room_depth=int(depth or 1),
            description_base=(description_base or "").strip(),
        )
        raw = await self.llm_client.generate(
            prompt,
            system_prompt="You output only a single image-generation prompt for Stable Diffusion or ComfyUI. No quotes, markdown, labels, or preamble.",
            max_tokens=400,
        )
        text = (raw or "").strip().strip('"').strip("'")
        text = " ".join(text.split())
        if len(text) < 8:
            return {"ok": False, "error": "llm_prompt_too_short", "detail": text or "(empty)"}
        return {"ok": True, "prompt": text[:2000]}

    async def play_suggest_portrait_prompt(
        self,
        username: str,
        password: str,
        character_name: str,
        appearance_notes: str = "",
    ) -> dict[str, Any]:
        """LLM: single-line ComfyUI-style portrait prompt from name and optional notes."""
        username = (username or "").strip()
        if not username:
            return {"ok": False, "error": "username_required"}
        async with self.db.session_factory() as db_session:
            account = await self._authenticate_account(db_session, username, password)
            if account is None:
                return {"ok": False, "error": "invalid_credentials"}

        cn = (character_name or "").strip() or "?"
        notes = (appearance_notes or "").strip()
        prompt = self.prompt_manager.render(
            "forge_portrait_character_prompt",
            character_name=cn,
            appearance_notes=notes or "(none)",
        )
        try:
            raw = await self.llm_client.generate(
                prompt,
                system_prompt=(
                    "You output only a single image-generation prompt for a character portrait "
                    "(headshot or bust). No quotes, markdown, labels, or preamble."
                ),
                max_tokens=400,
            )
        except Exception as e:
            logger.warning("play suggest portrait prompt LLM failed: %s", e, exc_info=True)
            return {"ok": False, "error": "llm_failed", "detail": str(e)}
        text = (raw or "").strip().strip('"').strip("'")
        text = " ".join(text.split())
        if len(text) < 8:
            return {"ok": False, "error": "llm_prompt_too_short", "detail": text or "(empty)"}
        return {"ok": True, "prompt": text[:2000]}

    async def play_suggest_scene_prompt(
        self,
        username: str,
        password: str,
        narrative_context: str = "",
        room_hint: str = "",
    ) -> dict[str, Any]:
        """LLM: ComfyUI-style environment prompt from recent narrative text."""
        username = (username or "").strip()
        if not username:
            return {"ok": False, "error": "username_required"}
        async with self.db.session_factory() as db_session:
            account = await self._authenticate_account(db_session, username, password)
            if account is None:
                return {"ok": False, "error": "invalid_credentials"}

        ctx = (narrative_context or "").strip()
        if len(ctx) > 8000:
            ctx = ctx[:8000]
        rh = (room_hint or "").strip() or "Unknown location"
        prompt = self.prompt_manager.render(
            "play_scene_image_prompt",
            narrative_context=ctx or "(no narrative text yet)",
            room_hint=rh,
        )
        try:
            raw = await self.llm_client.generate(
                prompt,
                system_prompt=(
                    "You output only a single image-generation prompt for an environment or scene. "
                    "No quotes, markdown, labels, or preamble."
                ),
                max_tokens=500,
            )
        except Exception as e:
            logger.warning("play suggest scene prompt LLM failed: %s", e, exc_info=True)
            return {"ok": False, "error": "llm_failed", "detail": str(e)}
        text = (raw or "").strip().strip('"').strip("'")
        text = " ".join(text.split())
        if len(text) < 8:
            return {"ok": False, "error": "llm_prompt_too_short", "detail": text or "(empty)"}
        return {"ok": True, "prompt": text[:2000]}

    async def play_generate_scene_image(
        self,
        username: str,
        password: str,
        scene_prompt: str,
        character_id: int | None = None,
    ) -> dict[str, Any]:
        """ComfyUI area workflow: save PNG under /media/rooms/ (or room-art); optional character_id persists URL for reload."""
        username = (username or "").strip()
        if not username:
            return {"ok": False, "error": "username_required"}
        async with self.db.session_factory() as db_session:
            account = await self._authenticate_account(db_session, username, password)
            if account is None:
                return {"ok": False, "error": "invalid_credentials"}
            account_id = account.id
        ip = (scene_prompt or "").strip()
        if len(ip) < 3:
            return {"ok": False, "error": "prompt_too_short"}
        if len(ip) > 4000:
            return {"ok": False, "error": "prompt_too_long"}
        cfg = self.config.comfyui
        area_wp = (cfg.area_workflow_path or "").strip() or cfg.workflow_path
        if not cfg.enabled or not resolve_config_asset_path(area_wp).is_file():
            return {
                "ok": False,
                "error": "comfyui_not_configured",
                **self._economy_public_fields(),
                "echo_credits": await self._echo_read_balance(account_id),
            }
        cost = int(cfg.area_generation_cost)
        ok_debit, err_debit, bal_after, charged = await self._echo_debit_for_generation(
            account_id, cost
        )
        if not ok_debit:
            return err_debit
        res = await self.forge_generate_room_area_image(ip)
        if not res.get("ok"):
            if charged:
                await self._echo_refund(account_id, charged)
            return {
                **res,
                **self._economy_public_fields(),
                "echo_credits": await self._echo_read_balance(account_id),
            }
        scene_url = res.get("area_image_url")
        scene_url_str = str(scene_url).strip()[:2048] if scene_url else ""
        if scene_url and _safe_player_scene_storage_url(scene_url_str):
            async with self.db.session_factory() as db_session:
                db_session.add(
                    AccountSceneImage(
                        account_id=account_id,
                        image_url=scene_url_str,
                        character_id=character_id
                        if character_id is not None and character_id >= 1
                        else None,
                        prompt_preview=ip[:512] if ip else None,
                    )
                )
                if character_id is not None and character_id >= 1:
                    char = await db_session.get(Character, character_id)
                    if char is not None and char.account_id == account_id:
                        char.last_scene_image_url = scene_url_str
                await db_session.commit()
        return {
            "ok": True,
            "scene_image_url": scene_url,
            "bundled": bool(res.get("bundled")),
            **self._economy_public_fields(),
            "echo_credits": bal_after,
            "cost_charged": charged,
        }

    async def play_list_scene_gallery(self, username: str, password: str) -> dict[str, Any]:
        """List ComfyUI scene images recorded for this account (newest first)."""
        username = (username or "").strip()
        if not username:
            return {"ok": False, "error": "username_required"}
        async with self.db.session_factory() as db_session:
            account = await self._authenticate_account(db_session, username, password)
            if account is None:
                return {"ok": False, "error": "invalid_credentials"}
            aid = account.id
            q = (
                select(AccountSceneImage, Character.name)
                .outerjoin(Character, AccountSceneImage.character_id == Character.id)
                .where(AccountSceneImage.account_id == aid)
                .order_by(AccountSceneImage.created_at.desc())
                .limit(200)
            )
            rows = (await db_session.execute(q)).all()
        items = []
        for img, char_name in rows:
            ts = img.created_at
            items.append(
                {
                    "id": img.id,
                    "image_url": img.image_url,
                    "created_at": ts.isoformat() + "Z" if ts else None,
                    "character_id": img.character_id,
                    "character_name": char_name,
                    "prompt_preview": (img.prompt_preview or "")[:240],
                }
            )
        return {"ok": True, "items": items}

    async def play_apply_scene_from_gallery(
        self,
        username: str,
        password: str,
        gallery_id: int,
        character_id: int,
    ) -> dict[str, Any]:
        """Set the active scene image for a character from a row in this account's gallery."""
        username = (username or "").strip()
        if not username:
            return {"ok": False, "error": "username_required"}
        if gallery_id < 1 or character_id < 1:
            return {"ok": False, "error": "invalid_ids"}
        async with self.db.session_factory() as db_session:
            account = await self._authenticate_account(db_session, username, password)
            if account is None:
                return {"ok": False, "error": "invalid_credentials"}
            aid = account.id
            row = await db_session.get(AccountSceneImage, gallery_id)
            if row is None or row.account_id != aid:
                return {"ok": False, "error": "gallery_item_not_found"}
            url = (row.image_url or "").strip()[:2048]
            if not _safe_player_scene_storage_url(url):
                return {"ok": False, "error": "invalid_stored_url"}
            char = await db_session.get(Character, character_id)
            if char is None or char.account_id != aid:
                return {"ok": False, "error": "character_not_owned"}
            char.last_scene_image_url = url
            await db_session.commit()
        return {"ok": True, "scene_image_url": url}

    async def forge_generate_room_area_image(
        self,
        image_prompt: str,
        *,
        zone_id: str = "",
        room_slug: str = "",
    ) -> dict[str, Any]:
        """ComfyUI: save PNG; optional zone+slug writes next to room YAML for portable world content."""
        cfg = self.config.comfyui
        area_wp = (cfg.area_workflow_path or "").strip() or cfg.workflow_path
        ip = (image_prompt or "").strip()
        zid = (zone_id or "").strip()
        rslug = (room_slug or "").strip().removesuffix(".yaml")
        seg_ok = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}$")
        bundle = bool(zid and rslug and seg_ok.match(zid) and seg_ok.match(rslug))
        area_resolved = resolve_config_asset_path(area_wp)
        logger.info(
            "forge room-area-image: enabled=%s area_workflow=%s resolved=%s exists=%s prompt_len=%s bundle=%s",
            cfg.enabled,
            area_wp,
            area_resolved,
            area_resolved.is_file(),
            len(ip),
            bundle,
        )
        if not cfg.enabled or not area_resolved.is_file():
            return {"ok": False, "error": "comfyui_not_configured"}

        from fablestar.comfyui_client import generate_comfy_png

        try:
            png, _ = await generate_comfy_png(cfg, image_prompt, kind="area")
        except Exception as e:
            logger.warning("ComfyUI area image failed: %s", e, exc_info=True)
            return {"ok": False, "error": "comfyui_failed", "detail": str(e)}
        if bundle:
            zones_root = Path("content/world/zones").resolve()
            room_art_dir = Path("content/world/zones") / zid / "rooms" / "art" / rslug
            room_art_dir.mkdir(parents=True, exist_ok=True)
            gen_name = f"gen_{uuid.uuid4().hex[:12]}.png"
            dest = (room_art_dir / gen_name).resolve()
            try:
                dest.relative_to(zones_root)
            except ValueError:
                logger.warning("forge room-area-image: rejected path escape for %s/%s", zid, rslug)
                bundle = False
            else:
                dest.write_bytes(png)
                url = f"/media/room-art/{zid}/{rslug}/v/{gen_name}"
                logger.info("forge room-area-image: bundled %s", dest)
                return {"ok": True, "area_image_url": url, "bundled": True}
        out_dir = Path("data/rooms")
        out_dir.mkdir(parents=True, exist_ok=True)
        fname = f"{uuid.uuid4().hex}.png"
        dest = out_dir / fname
        dest.write_bytes(png)
        return {"ok": True, "area_image_url": f"/media/rooms/{fname}", "bundled": False}

    async def play_generate_portrait(
        self, username: str, password: str, appearance_prompt: str
    ) -> dict[str, Any]:
        username = (username or "").strip()
        if not username:
            return {"ok": False, "error": "username_required"}
        async with self.db.session_factory() as db_session:
            account = await self._authenticate_account(db_session, username, password)
            if account is None:
                return {"ok": False, "error": "invalid_credentials"}
            account_id = account.id

        cfg = self.config.comfyui
        eco = self._economy_public_fields()
        if not cfg.enabled or not resolve_config_asset_path(cfg.workflow_path).is_file():
            return {
                "ok": True,
                "portrait_url": None,
                "note": "comfyui_not_configured",
                **eco,
                "echo_credits": await self._echo_read_balance(account_id),
            }

        cost = int(cfg.portrait_generation_cost)
        ok_debit, err_debit, bal_after, charged = await self._echo_debit_for_generation(
            account_id, cost
        )
        if not ok_debit:
            return err_debit

        try:
            png, _ = await generate_portrait_png(cfg, appearance_prompt)
        except Exception as e:
            logger.warning("ComfyUI portrait failed: %s", e, exc_info=True)
            if charged:
                await self._echo_refund(account_id, charged)
            return {
                "ok": False,
                "error": "comfyui_failed",
                "detail": str(e),
                **eco,
                "echo_credits": await self._echo_read_balance(account_id),
            }

        return {
            "ok": True,
            "portrait_url": self._save_portrait_png(png),
            **eco,
            "echo_credits": bal_after,
            "cost_charged": charged,
        }

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

            reg0 = self.content_loader.get_proficiency_registry()
            ok_st, err_st = validate_starter_allocation(starter_clean, reg0)
            if not ok_st:
                return {"ok": False, "error": err_st}, {}
        return None, starter_clean

    @staticmethod
    def _save_portrait_png(png: bytes) -> str:
        """Write a generated portrait PNG under data/portraits and return its /media URL."""
        out_dir = Path("data/portraits")
        out_dir.mkdir(parents=True, exist_ok=True)
        fname = f"{uuid.uuid4().hex}.png"
        (out_dir / fname).write_bytes(png)
        return f"/media/portraits/{fname}"

    async def _generate_create_portrait(
        self, account_id: int, name: str, pp: str | None
    ) -> tuple[dict[str, Any] | None, str | None, str | None, str | None, int]:
        """ComfyUI portrait for character create (debit → generate → write → refund on failure).

        Returns (error_response, portrait_url, portrait_prompt, gen_failed_detail, charged).
        """
        cfg = self.config.comfyui
        if not (cfg.enabled and resolve_config_asset_path(cfg.workflow_path).is_file()):
            return None, None, pp, None, 0
        prompt_use = pp if pp else _default_character_portrait_prompt(name)
        cost_c = int(cfg.character_create_portrait_cost)
        ok_d, err_d, _bal_d, charged = await self._echo_debit_for_generation(account_id, cost_c)
        if not ok_d:
            return err_d, None, pp, None, 0
        try:
            png, _ = await generate_portrait_png(cfg, prompt_use)
            return None, self._save_portrait_png(png), pp or prompt_use, None, charged
        except Exception as e:
            if charged:
                await self._echo_refund(account_id, charged)
            logger.warning("ComfyUI portrait on character create failed: %s", e, exc_info=True)
            return None, None, pp, str(e), charged

    async def play_create_character(
        self,
        username: str,
        password: str,
        name: str,
        portrait_prompt: str = "",
        portrait_url: str = "",
        starter_proficiencies: dict[str, int] | None = None,
    ) -> dict[str, Any]:
        username = (username or "").strip()
        name = (name or "").strip()
        if not username:
            return {"ok": False, "error": "username_required"}
        err, p_url, pp = self._validate_create_character_inputs(name, portrait_url, portrait_prompt)
        if err:
            return err
        err, starter_clean = self._clean_starter_proficiencies(starter_proficiencies)
        if err:
            return err

        async with self.db.session_factory() as db_session:
            account = await self._authenticate_account(db_session, username, password)
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

        async with self.db.session_factory() as db_session:
            start_digi = int(self.config.server.starting_digi_balance)
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
                    self.content_loader.get_proficiency_registry(),
                )
            character.stats = merged_stats
            await db_session.commit()
            await db_session.refresh(character)
            payload = _character_play_dict(character)
            result = await db_session.execute(
                select(Character).where(Character.account_id == account_id).order_by(Character.id)
            )
            all_chars = [_character_play_dict(c) for c in result.scalars().all()]

        final_bal = await self._echo_read_balance(account_id)
        out: dict[str, Any] = {
            "ok": True,
            "character": payload,
            "characters": all_chars,
            **self._economy_public_fields(),
            "echo_credits": final_bal,
            "is_gm": is_gm,
        }
        if create_portrait_charged and not portrait_gen_failed:
            out["cost_charged"] = create_portrait_charged
        if portrait_gen_failed:
            out["portrait_generation_failed"] = True
            out["portrait_generation_detail"] = portrait_gen_failed
        return out

    async def play_delete_character(
        self, username: str, password: str, character_id: int
    ) -> dict[str, Any]:
        """Remove one character if it belongs to the authenticated account."""
        username = (username or "").strip()
        if not username:
            return {"ok": False, "error": "username_required"}
        if character_id is None or character_id < 1:
            return {"ok": False, "error": "character_id_invalid"}
        async with self.db.session_factory() as db_session:
            account = await self._authenticate_account(db_session, username, password)
            if account is None:
                return {"ok": False, "error": "invalid_credentials"}
            result = await db_session.execute(select(Character).where(Character.id == character_id))
            char = result.scalar_one_or_none()
            if char is None or char.account_id != account.id:
                return {"ok": False, "error": "character_not_found"}
            await db_session.delete(char)
            await db_session.commit()
            return await self._account_characters_response(db_session, account)

    async def play_refresh_characters(self, username: str, password: str) -> dict[str, Any]:
        """Re-list characters after create (same shape as login)."""
        username = (username or "").strip()
        if not username:
            return {"ok": False, "error": "username_required"}
        async with self.db.session_factory() as db_session:
            account = await self._authenticate_account(db_session, username, password)
            if account is None:
                return {"ok": False, "error": "invalid_credentials"}
            return await self._account_characters_response(db_session, account)

    async def _bootstrap_session(self, session: Session, character: _CharSnapshot):
        """Link the session, seed Redis from the character record, and send the opening view."""
        self.session_manager.link_player(session.id, character.name)

        from fablestar.proficiencies.state_helpers import (
            ensure_proficiency_block,
            migrate_legacy_stats,
            total_proficiency_levels,
        )

        norm_stats = migrate_legacy_stats(dict(character.stats))
        ensure_proficiency_block(norm_stats)
        character.stats = norm_stats

        # Seed Redis with the character's current state
        await self.redis.set_player_location(character.name, character.room_id)
        await self.redis.set_player_stats(character.name, norm_stats)
        await self.redis.set_player_inventory(character.name, character.inventory)

        try:
            reg = self.content_loader.get_proficiency_registry()
            total_lv = total_proficiency_levels(norm_stats, registry=reg)
        except Exception:
            total_lv = total_proficiency_levels(norm_stats)
        from fablestar.network.play_messages import CharacterSnapshotNotice

        snapshot: CharacterSnapshotNotice = {
            "client_notice": "character_snapshot",
            "character_name": character.name,
            "stats": norm_stats,
            "resonance_levels_total": total_lv,
        }
        await session.send(json.dumps(snapshot) + "\r\n")

        # Initial look
        await self.dispatcher.dispatch(session, "look")
        await session.send_prompt()

    async def _session_loop(self, session: Session):
        """Main input/output loop for a single session: authenticate → bootstrap → command loop."""
        try:
            character = await self._authenticate_websocket(session)
            if character is None:
                return

            await self._bootstrap_session(session, character)

            while session.protocol.is_connected:
                line = await session.protocol.receive()
                if line is None:
                    break

                if line:
                    await self.dispatcher.dispatch(session, line)

                await session.send_prompt()

        except Exception as e:
            logger.error(f"Error in session loop for {session.id}: {e}", exc_info=True)
        finally:
            # Final sync to DB before the session tears down
            if session.player_id:
                await self.persistence.sync_character(session.player_id)
            await self.session_manager.destroy_session(session.id)

    async def _on_file_changed(self, path: Path):
        """Handle hot-reload requests from the watcher."""
        logger.info(f"Hot-reload triggered for: {path}")

        if "content" in path.parts:
            self.content_loader.invalidate(path)

        if "prompts" in path.parts:
            self.prompt_manager.reload()

        if "commands" in path.parts:
            # path is something like f:/.../fablestar/commands/info.py
            # we need "fablestar.commands.info"
            parts = path.parts
            try:
                # Find where 'fablestar' starts to build the module path
                idx = parts.index("fablestar")
                module_path = ".".join(parts[idx:]).removesuffix(".py")
                registry.reload_module(module_path)
            except ValueError:
                logger.error(f"Could not determine module path for {path}")


async def run_server():
    """Entry point for running the server in an event loop."""
    import os
    from logging.handlers import RotatingFileHandler

    # Ensure logs directory
    os.makedirs("logs", exist_ok=True)

    # Setup dual logging (Console + File)
    log_formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%H:%M:%S"
    )

    # Console Handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_formatter)

    # File Handler (Persistent logging for the AI Architect)
    file_handler = RotatingFileHandler("logs/engine.log", maxBytes=5 * 1024 * 1024, backupCount=3)
    file_handler.setFormatter(log_formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    server = FablestarServer()
    app.app_instance = server  # must be set before commands import app_instance
    await server.startup()

    # Await both long-running tasks (nexus HTTP + tick loop).
    try:
        tasks = [t for t in (server._nexus_task, server._tick_task) if t]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    finally:
        await server.shutdown()
