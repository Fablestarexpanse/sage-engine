"""SageServer — owns all subsystems and drives the startup/shutdown lifecycle.

Play/forge API logic lives in the composed services (see sage.services):
economy (echo credits), player (accounts/characters), scenes (ComfyUI images + LLM suggests).
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select

from sage import app, lexicon
from sage.admin import content_browser
from sage.admin.nexus import NexusApp
from sage.agents.manager import AgentManager
from sage.bootstrap import ensure_dev_defaults
from sage.commands.registry import registry
from sage.core.comfyui_persist import save_comfyui_toml
from sage.core.config import ComfyUIConfig, Config, LLMConfig, load_config, resolve_project_root
from sage.core.events import EventBus, SessionEnded, SessionStarted, emit
from sage.core.llm_persist import save_llm_toml
from sage.core.resolvers import Resolvers
from sage.core.tick import TickManager
from sage.effects.manager import EffectsManager
from sage.hot_reload import HotReloader
from sage.llm.client import LLMClient
from sage.llm.prompts import PromptManager
from sage.network.session import Session, SessionManager
from sage.parser.dispatcher import CommandDispatcher
from sage.plugins import PluginHost
from sage.services._shared import resolve_play_account
from sage.services.economy import EconomyService
from sage.services.player_service import PlayerService
from sage.services.scene_service import SceneService
from sage.state.models import Character
from sage.state.persistence import PersistenceManager
from sage.state.postgres import PostgresState
from sage.state.redis_client import RedisState
from sage.world.ambient import AmbientManager
from sage.world.loader import ContentLoader
from sage.world.package import select_world
from sage.world.spawner import EntitySpawnManager
from sage.world.wallet import Wallet

logger = logging.getLogger(__name__)

# The engine package directory (hot reload watches and resolves command modules from here).
PACKAGE_DIR = Path(__file__).resolve().parent


@dataclass
class _CharSnapshot:
    """Plain snapshot of ORM Character data usable after the SQLAlchemy session closes."""

    name: str
    room_id: str
    stats: dict[str, Any]
    inventory: list[Any]
    digi_balance: int = 0


def _snapshot_from_orm(character: Any) -> _CharSnapshot:
    return _CharSnapshot(
        name=character.name,
        room_id=character.room_id,
        stats=dict(character.stats or {}),
        inventory=list(character.inventory or []),
        digi_balance=int(character.digi_balance or 0),
    )


class SageServer:
    """
    Main orchestration class for the SAGE engine.
    Ties together core systems and manages the server lifecycle.
    """

    def __init__(self, config: Config | None = None):
        self.config = config or load_config()
        # The world package this deployment runs (docs/sage/PHASE1_CONTRACTS.md Part B).
        self.project_root = resolve_project_root()
        self.world = select_world(
            self.project_root / self.config.server.worlds_dir, self.config.server.world
        )
        self.tick_manager = TickManager(tick_rate=self.config.server.tick_rate)
        self.events = EventBus()
        self.resolvers = Resolvers()
        self._define_engine_resolvers()
        self.session_manager = SessionManager()
        self.redis = RedisState(self.config.redis)
        self.db = PostgresState(self.config.database)
        self.persistence = PersistenceManager(self)
        # In-world money in the world's currencies (sage.world.wallet).
        self.wallet = Wallet(self.world, self.redis)
        self.content_loader = ContentLoader(self.world.content_dir)
        content_browser.set_content_root(self.world.content_dir)
        self.spawner = EntitySpawnManager(self)
        self.ambient = AmbientManager(self)
        self.effects = EffectsManager(self)
        self.agent_manager = AgentManager(self)
        self.hot_reloader = HotReloader(self._on_file_changed)
        self.dispatcher = CommandDispatcher(events=self.events)
        self.plugins = PluginHost(
            world=self.world,
            registry=registry,
            events=self.events,
            resolvers=self.resolvers,
            tick_manager=self.tick_manager,
            redis=self.redis,
            content=self.content_loader,
            server=self,
            plugins_root=self.project_root / "plugins",
            trusted_roots=[self.project_root / "plugins", self.project_root / "worlds"],
        )
        self.nexus = NexusApp(self)
        self.plugins.http = self.nexus.app

        # LLM Subsystems
        self.llm_client = LLMClient(self.config.llm)
        # One shared in-process GGUF serves narration AND agent brains when
        # either selects the "embedded" backend (model loads once).
        self._embedded_llm = None
        self.llm_client.embedded_getter = self.embedded_llm
        # Secondary LLM profile (config/agents_llm.toml) for character speech and plans.
        from sage.llm.profiles import LLMProfile

        self.llm_profile = LLMProfile(self)
        self.prompt_manager = PromptManager(self.world.prompts_dir)
        from sage.lexicon.overrides import LexiconOverrides

        self.lexicon_overrides = LexiconOverrides(self.db.session_factory)
        self._active_lexicon_overrides: dict[str, str] = {}
        self.lexicon = self._build_lexicon()

        # Domain services (each reads config/db through this server so live
        # settings updates are always observed)
        self.economy = EconomyService(self)
        self.player = PlayerService(self)
        self.scenes = SceneService(self)

        # Internal state
        self._nexus_task: asyncio.Task | None = None
        self._tick_task: asyncio.Task | None = None
        # ISO8601 UTC timestamp of last POST /content/cache/reload (for admin UI)
        self.last_content_reload_at: str | None = None

    # ------------------------------------------------------------------
    # Play-client notifications (admin actions → connected sessions)
    # ------------------------------------------------------------------

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
        from sage.network.session import SessionState

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
            **self.economy.public_fields(),
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
            **self.economy.public_fields(),
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

    # ------------------------------------------------------------------
    # Live settings updates
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def startup(self):
        """Initialize and start all sub-systems."""
        logger.info("SAGE engine starting up...")
        manifest = self.world.manifest.world
        logger.info(
            "World: %s (%s %s) from %s",
            manifest.id,
            manifest.name,
            manifest.version,
            self.world.root,
        )

        # 0. State stores — Redis must be ready before EntitySpawnManager and PersistenceManager
        await self.redis.connect()

        # 0b. The world's plugins are validated first, and the database must already carry every
        #     core and plugin migration (contracts C.3 step 4: never auto-migrate on boot).
        plugin_records = self.plugins.discover()
        await self._require_migrated(plugin_records)

        # 0a. Bootstrap dev accounts (requires Postgres; best-effort, never fatal)
        await ensure_dev_defaults(self.db, self.config)

        # 1. Command registry — must complete before NexusApp handles any WebSocket connections
        registry.load_module_strict("sage.commands.info")
        registry.load_module_strict("sage.commands.communication")
        registry.load_module_strict("sage.commands.movement")
        registry.load_module_strict("sage.commands.combat")
        registry.load_module_strict("sage.commands.items")
        registry.load_module_strict("sage.commands.proficiency")
        registry.load_module_strict("sage.commands.effects")
        registry.load_module_strict("sage.commands.admin")

        # 1b. The world's plugins, after engine commands so verb conflicts are caught.
        self.plugins.load(plugin_records)
        await self.reload_lexicon_overrides()

        # 2. Tick handlers — must be registered before the tick loop starts in step 4
        self.tick_manager.register(self.spawner.on_tick)
        self.tick_manager.register(self.ambient.on_tick)
        self.tick_manager.register(self.effects.on_tick)
        self.tick_manager.register(self.agent_manager.on_tick)
        self.tick_manager.register(self.persistence.on_tick)

        # 3. HotReloader — watches content/ and commands/; safe to start any time after step 1
        await self.hot_reloader.start(
            [
                str(self.world.content_dir),
                str(PACKAGE_DIR / "commands"),
                str(self.project_root / "config"),
                str(self.world.prompts_dir),
                str(self.world.lexicon_dir),
            ]
        )

        # 4. NexusApp (FastAPI HTTP + WebSocket) — requires command registry (step 1) to be ready
        self._nexus_task = asyncio.create_task(self.nexus.start())

        # 5. Tick loop — requires tick handlers registered (step 2) and Redis connected (step 0)
        self._tick_task = asyncio.create_task(self.tick_manager.run())

        logger.info("Startup complete. Server is running.")

    async def shutdown(self):
        """Gracefully stop all sub-systems."""
        logger.info("SAGE engine shutting down...")

        self.hot_reloader.stop()
        self.tick_manager.stop()
        self.plugins.teardown()
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

    # ------------------------------------------------------------------
    # WebSocket play session
    # ------------------------------------------------------------------

    async def _authenticate_websocket(self, session: Session) -> _CharSnapshot | None:
        """
        WebSocket player: first message must be JSON:
        {"token"} (play session token from login) or {"username","password"},
        plus optional "character_id" when the account has several characters.
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
        token = (data.get("token") or "").strip()
        char_id_raw = data.get("character_id")
        char_id: int | None = None
        if char_id_raw is not None:
            try:
                char_id = int(char_id_raw)
            except (TypeError, ValueError):
                char_id = None
        if not username and not token:
            await session.send(json.dumps({"ok": False, "error": "username_required"}) + "\r\n")
            return None

        async with self.db.session_factory() as db_session:
            account = await resolve_play_account(
                db_session, self, token=token, username=username, password=password
            )
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

            # Agents and players share the name-keyed state; a character row
            # that predates the name guard must not take over a resident agent.
            try:
                agent_names = {
                    p.name.lower() for p in self.content_loader.get_agent_registry().all()
                }
            except Exception:
                agent_names = set()
            if character.name.lower() in agent_names:
                await session.send(
                    json.dumps({"ok": False, "error": "character_name_reserved"}) + "\r\n"
                )
                return None

            account.last_login = datetime.utcnow()
            await db_session.commit()
            await db_session.refresh(character)

        return _snapshot_from_orm(character)

    async def _bootstrap_session(self, session: Session, character: _CharSnapshot):
        """Link the session, seed Redis from the character record, and send the opening view."""
        await self.session_manager.kick_existing(character.name)
        self.session_manager.link_player(session.id, character.name)

        from sage.proficiencies.state_helpers import (
            ensure_proficiency_block,
            migrate_legacy_stats,
        )

        norm_stats = migrate_legacy_stats(dict(character.stats))
        ensure_proficiency_block(norm_stats)
        # Canonical vitals: nothing else seeds them, and every consumer was
        # falling back to a different default (combat 20, client bar 100).
        norm_stats.setdefault("max_hp", 100)
        norm_stats.setdefault("hp", int(norm_stats["max_hp"]))
        character.stats = norm_stats

        # Death recovery: a character persisted at 0 hp wakes in the medbay at
        # half health with death-bound effects cleared, instead of logging in
        # as a corpse that dies to the first breeze.
        respawned = False
        respawn_bill = 0
        if self.resolvers.get("death.check")(norm_stats):
            from sage.effects.engine import clear_on_death

            clear_on_death(norm_stats)
            plan = self.resolvers.get("death.respawn")(
                self.world, norm_stats, int(character.digi_balance or 0)
            )
            norm_stats["hp"] = plan.hp
            if self.content_loader.get_room(plan.room_id) is not None:
                character.room_id = plan.room_id
            character.digi_balance = int(character.digi_balance or 0) - plan.bill
            respawned = True
            respawn_bill = plan.bill

        # A character saved in a room that no longer exists (zone deleted or
        # renamed) wakes at the world start instead of a void.
        if self.content_loader.get_room(character.room_id) is None:
            logger.info(
                "Character %s was in missing room %s; moving to %s",
                character.name,
                character.room_id,
                self.world.start_room,
            )
            character.room_id = self.world.start_room

        # In-world wallet: the DB column is the durable copy of the primary balance until the
        # JSONB state step; the stats blob is what the wallet spends from (PersistenceManager
        # mirrors it back).
        if self.wallet.enabled:
            self.wallet.set(norm_stats, int(character.digi_balance or 0))

        # Seed Redis with the character's current state
        await self.redis.set_player_location(character.name, character.room_id)
        await self.redis.set_player_stats(character.name, norm_stats)
        await self.redis.set_player_inventory(character.name, character.inventory)

        if respawned:
            currency = self.wallet.name() if self.wallet.enabled else ""
            bill = (
                lexicon.t("death.bill", amount=respawn_bill, currency=currency)
                if respawn_bill
                else lexicon.t("death.no_bill")
            )
            await session.say("death.wake", bill=bill)

        await self.push_character_snapshot(session)

        for key in ("login.banner", "login.motd"):
            if text := lexicon.t(key).strip():
                await session.send(text)

        await emit(self, SessionStarted(player_id=character.name))

        # Initial look
        await self.dispatcher.dispatch(session, "look")
        if not norm_stats.get("visited_rooms"):
            await session.say("onboarding.new_player")
        await session.send_prompt()

    async def push_character_snapshot(self, session: Session) -> None:
        """Send the live character_snapshot notice that drives the client side panels."""
        import time as _time

        from sage.effects.engine import ensure_effects
        from sage.network.play_messages import CharacterSnapshotNotice
        from sage.proficiencies.state_helpers import total_proficiency_levels

        player_id = session.player_id
        if not player_id:
            return
        # Agents have no UI; JSON snapshots would only pollute their
        # perception buffers (and push real say lines out of the voice window).
        if getattr(session, "virtual", False):
            return
        try:
            stats = await self.redis.get_player_stats(player_id)
            inventory = await self.redis.get_player_inventory(player_id)
            room_id = await self.redis.get_player_location(player_id)
            room = self.content_loader.get_room(room_id) if room_id else None

            try:
                reg = self.content_loader.get_proficiency_registry()
                total_lv = total_proficiency_levels(stats, registry=reg)
            except Exception:
                total_lv = total_proficiency_levels(stats)

            now = _time.time()
            effects = [
                {
                    "name": e.get("name", "?"),
                    "description": e.get("description", ""),
                    "debuff": bool(e.get("debuff", True)),
                    "seconds_left": (
                        None if e.get("expires_at") is None else max(0, int(e["expires_at"] - now))
                    ),
                }
                for e in ensure_effects(stats)
            ]

            # Visited tracking for the client map (list-as-set in the stats blob).
            visited = stats.get("visited_rooms")
            if not isinstance(visited, list):
                visited = []
            if room_id and room_id not in visited:
                visited.append(room_id)
                del visited[:-300]
                stats["visited_rooms"] = visited
                await self.redis.set_player_stats(player_id, stats)

            snapshot: CharacterSnapshotNotice = {
                "client_notice": "character_snapshot",
                "character_name": player_id,
                "stats": stats,
                "resonance_levels_total": total_lv,
                "location": {
                    "id": room_id or "",
                    "name": room.name if room and room.name else None,
                },
                "effects": effects,
                "inventory": list(inventory),
                "map": self._zone_map(room_id, set(visited)) if room_id else None,
            }
            await session.send(json.dumps(snapshot) + "\r\n")
        except Exception:
            logger.debug("character_snapshot push failed for %s", player_id, exc_info=True)

    def embedded_llm(self):
        """Lazy shared EmbeddedLLM (config from agents_llm: model_path etc.)."""
        if self._embedded_llm is None:
            from sage.llm.embedded import EmbeddedLLM

            self._embedded_llm = EmbeddedLLM(self.config.agents_llm)
        return self._embedded_llm

    def _zone_map(self, current_room_id: str, visited: set[str]) -> dict | None:
        """
        Zone map for the client MAP panel: rooms with editor x/y positions plus
        internal exit edges. Geometry is cached per zone (cleared with the
        content cache on hot reload); the per-player visited flags are applied
        per call.
        """
        try:
            zone, _, _ = current_room_id.partition(":")
            if not zone:
                return None
            cache_key = f"client_map:{zone}"
            cached = self.content_loader._cache.get(cache_key)
            if cached is None:
                import json as _json

                rooms_dir = self.world.zones_dir / zone / "rooms"
                if not rooms_dir.is_dir():
                    return None
                positions = {}
                pos_path = rooms_dir.parent / ".positions.json"
                if pos_path.is_file():
                    doc = _json.loads(pos_path.read_text(encoding="utf-8"))
                    positions = doc.get("positions", {}) or {}
                rooms = []
                edges: set[tuple[str, str]] = set()
                for f in sorted(rooms_dir.glob("*.yaml")):
                    rid = f"{zone}:{f.stem}"
                    room = self.content_loader.get_room(rid)
                    if room is None:
                        continue
                    pos = positions.get(f.stem, {})
                    rooms.append(
                        {
                            "id": rid,
                            "name": room.name or f.stem,
                            "x": float(pos.get("x", 0.0)),
                            "y": float(pos.get("y", 0.0)),
                        }
                    )
                    for ex in room.exits.values():
                        dest = ex.destination
                        if dest.startswith(f"{zone}:"):
                            edges.add(tuple(sorted((rid, dest))))
                cached = {"zone": zone, "rooms": rooms, "edges": sorted(edges)}
                self.content_loader._cache[cache_key] = cached
            return {
                "zone": cached["zone"],
                "current": current_room_id,
                "rooms": [{**r, "visited": r["id"] in visited} for r in cached["rooms"]],
                "edges": [list(e) for e in cached["edges"]],
            }
        except Exception:
            logger.debug("zone map build failed for %s", current_room_id, exc_info=True)
            return None

    async def run_session_loop(self, session: Session):
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
                    # Keep the client's side panels in sync after every command.
                    await self.push_character_snapshot(session)

                await session.send_prompt()

        except Exception as e:
            logger.error(f"Error in session loop for {session.id}: {e}", exc_info=True)
        finally:
            # Final sync to DB before the session tears down
            # A session evicted by a newer login must not tear down the state
            # the new session is now using (room set, DB sync).
            if session.player_id and self.session_manager.owns_player(session):
                await emit(self, SessionEnded(player_id=session.player_id))
                await self.persistence.sync_character(session.player_id)
                # Ghost fix: leaving the game must leave the room too, or the
                # room's player set keeps a phantom occupant forever.
                try:
                    room_id = await self.redis.get_player_location(session.player_id)
                    if room_id:
                        await self.redis.remove_player_from_room(session.player_id, room_id)
                except Exception:
                    logger.debug("Room-set cleanup failed for %s", session.player_id, exc_info=True)
            await self.session_manager.destroy_session(session.id)

    async def _require_migrated(self, plugin_records) -> None:
        from sage.plugins.migrations import (
            alembic_config,
            pending_heads_async,
            unexpected_tables_async,
        )
        from sage.state.postgres import Base

        cfg = alembic_config([r.path for r in plugin_records])
        pending = await pending_heads_async(cfg, self.db.url)
        if pending:
            raise RuntimeError(
                f"Database {self.config.database.database!r} is missing migrations "
                f"(unapplied heads: {', '.join(pending)}). Run: python -m sage db upgrade"
            )
        strays = await unexpected_tables_async(
            self.db.url, Base.metadata.tables.keys(), [r.id for r in plugin_records]
        )
        if strays:
            logger.warning(
                "Tables owned by neither the engine nor an enabled plugin: %s", ", ".join(strays)
            )

    def _define_engine_resolvers(self) -> None:
        """Engine resolver slots and their defaults (contracts catalog #4)."""
        from sage.world.death import default_death_check, default_respawn

        self.resolvers.define("death.check", default_death_check)
        self.resolvers.define("death.respawn", default_respawn)

        from sage.proficiencies.field_gain import skill_level, skill_used
        from sage.world.progression import (
            SKILL_LEVEL,
            SKILL_USED,
            default_skill_level,
            default_skill_used,
        )

        self.resolvers.define(SKILL_USED, default_skill_used)
        self.resolvers.define(SKILL_LEVEL, default_skill_level)
        # Transitional: the proficiency system is still engine code and answers for every world
        # until it moves into a world progression plugin (phase-3 plan), which will provide these.
        self.resolvers.provide(SKILL_USED, skill_used, owner="proficiencies")
        self.resolvers.provide(SKILL_LEVEL, skill_level, owner="proficiencies")

        from sage.proficiencies.state_helpers import seed_attributes, skill_sheet, total_levels
        from sage.world.progression import (
            SEED_ATTRIBUTES,
            SKILL_SHEET,
            TOTAL_LEVELS,
            default_seed_attributes,
            default_skill_sheet,
            default_total_levels,
        )

        self.resolvers.define(SEED_ATTRIBUTES, default_seed_attributes)
        self.resolvers.define(TOTAL_LEVELS, default_total_levels)
        self.resolvers.define(SKILL_SHEET, default_skill_sheet)
        self.resolvers.provide(SEED_ATTRIBUTES, seed_attributes, owner="proficiencies")
        self.resolvers.provide(TOTAL_LEVELS, total_levels, owner="proficiencies")
        self.resolvers.provide(SKILL_SHEET, skill_sheet, owner="proficiencies")

    async def reload_lexicon_overrides(self) -> None:
        """Re-read active Nexus lexicon edits and rebuild the live lexicon (no restart)."""
        self._active_lexicon_overrides = await self.lexicon_overrides.active()
        self.lexicon = self._build_lexicon()

    def _build_lexicon(self) -> lexicon.Lexicon:
        """World strings over engine defaults; installed for Session.say and lexicon.t."""
        plugin_layers = self.plugins.lexicon_layers() if hasattr(self, "plugins") else []
        built = lexicon.build_lexicon(
            self.world.lexicon_dir,
            self.world.manifest.world.locale,
            overrides=getattr(self, "_active_lexicon_overrides", None),
            plugin_layers=plugin_layers,
        )
        lexicon.set_active(built)
        return built

    async def _on_file_changed(self, path: Path):
        """Handle hot-reload requests from the watcher."""
        logger.info(f"Hot-reload triggered for: {path}")

        world = getattr(self, "world", None)
        if world is not None and path.resolve().is_relative_to(world.lexicon_dir):
            self.lexicon = self._build_lexicon()

        if world is not None and path.resolve().is_relative_to(world.content_dir):
            self.content_loader.invalidate(path)

        if world is not None and path.resolve().is_relative_to(world.prompts_dir):
            self.prompt_manager.reload()

        if "commands" in path.parts:
            # path is <package dir>/commands/info.py -> module "<package>.commands.info",
            # derived from where this package lives so a move or rename can't break it.
            try:
                relative = path.resolve().relative_to(PACKAGE_DIR)
                module_path = ".".join((__package__, *relative.with_suffix("").parts))
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

    server = SageServer()
    app.app_instance = server  # must be set before commands import app_instance
    await server.startup()

    # Await both long-running tasks (nexus HTTP + tick loop).
    try:
        tasks = [t for t in (server._nexus_task, server._tick_task) if t]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    finally:
        await server.shutdown()
