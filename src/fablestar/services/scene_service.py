"""SceneService — ComfyUI status/ping, portrait and scene image generation, LLM prompt suggests."""

from __future__ import annotations

import json
import logging
import re
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
from sqlalchemy import select

from fablestar.comfyui_client import generate_portrait_png
from fablestar.core.config import resolve_config_asset_path
from fablestar.llm.client import LLMGenerationError
from fablestar.services._shared import (
    resolve_play_account,
    resolve_play_account_or_error,
    save_portrait_png,
)
from fablestar.state.models import AccountSceneImage, Character

if TYPE_CHECKING:
    from fablestar.server import FablestarServer

logger = logging.getLogger(__name__)


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


def _is_safe_player_scene_storage_url(url: str | None) -> bool:
    """Only allow persisting Nexus-served paths we write under data/ or bundled room-art."""
    u = (url or "").strip()
    if not u.startswith("/media/") or ".." in u or len(u) > 2048:
        return False
    return u.startswith("/media/rooms/") or u.startswith("/media/room-art/")


class SceneService:
    """AI image generation for the player UI and WorldForge (ComfyUI + LLM prompt suggests)."""

    def __init__(self, server: FablestarServer):
        self.server = server

    # ------------------------------------------------------------------
    # ComfyUI status
    # ------------------------------------------------------------------

    async def comfyui_status(self) -> dict[str, Any]:
        c = self.server.config.comfyui
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

    async def ping(self) -> tuple[bool, str]:
        """Return (reachable, error_message) for the configured ComfyUI base URL."""
        return await _ping_comfyui_http(self.server.config.comfyui.base_url)

    # ------------------------------------------------------------------
    # LLM prompt suggestions
    # ------------------------------------------------------------------

    async def forge_suggest_area_image_prompt(
        self,
        room_name: str,
        room_type: str,
        depth: int,
        description_base: str,
    ) -> dict[str, Any]:
        """LM Studio / OpenAI-compatible: short ComfyUI prompt from room fields."""
        prompt = self.server.prompt_manager.render(
            "forge_area_image_prompt",
            room_name=room_name or "?",
            room_type=room_type or "chamber",
            room_depth=int(depth or 1),
            description_base=(description_base or "").strip(),
        )
        try:
            raw = await self.server.llm_client.generate_or_raise(
                prompt,
                system_prompt="You output only a single image-generation prompt for Stable Diffusion or ComfyUI. No quotes, markdown, labels, or preamble.",
                max_tokens=400,
            )
        except LLMGenerationError as e:
            logger.warning("forge area image prompt LLM failed: %s", e)
            return {"ok": False, "error": "llm_failed", "detail": str(e)}
        text = (raw or "").strip().strip('"').strip("'")
        text = " ".join(text.split())
        if len(text) < 8:
            return {"ok": False, "error": "llm_prompt_too_short", "detail": text or "(empty)"}
        return {"ok": True, "prompt": text[:2000]}

    async def suggest_portrait_prompt(
        self,
        username: str,
        password: str,
        character_name: str,
        appearance_notes: str = "",
        token: str = "",
    ) -> dict[str, Any]:
        """LLM: single-line ComfyUI-style portrait prompt from name and optional notes."""
        _account, err = await resolve_play_account_or_error(
            self.server, token=token, username=username, password=password
        )
        if err:
            return err

        cn = (character_name or "").strip() or "?"
        notes = (appearance_notes or "").strip()
        prompt = self.server.prompt_manager.render(
            "forge_portrait_character_prompt",
            character_name=cn,
            appearance_notes=notes or "(none)",
        )
        try:
            raw = await self.server.llm_client.generate_or_raise(
                prompt,
                system_prompt=(
                    "You output only a single image-generation prompt for a character portrait "
                    "(headshot or bust). No quotes, markdown, labels, or preamble."
                ),
                max_tokens=400,
            )
        except LLMGenerationError as e:
            logger.warning("play suggest portrait prompt LLM failed: %s", e)
            return {"ok": False, "error": "llm_failed", "detail": str(e)}
        text = (raw or "").strip().strip('"').strip("'")
        text = " ".join(text.split())
        if len(text) < 8:
            return {"ok": False, "error": "llm_prompt_too_short", "detail": text or "(empty)"}
        return {"ok": True, "prompt": text[:2000]}

    async def suggest_scene_prompt(
        self,
        username: str,
        password: str,
        narrative_context: str = "",
        room_hint: str = "",
        token: str = "",
    ) -> dict[str, Any]:
        """LLM: ComfyUI-style environment prompt from recent narrative text."""
        _account, err = await resolve_play_account_or_error(
            self.server, token=token, username=username, password=password
        )
        if err:
            return err

        ctx = (narrative_context or "").strip()
        if len(ctx) > 8000:
            ctx = ctx[:8000]
        rh = (room_hint or "").strip() or "Unknown location"
        prompt = self.server.prompt_manager.render(
            "play_scene_image_prompt",
            narrative_context=ctx or "(no narrative text yet)",
            room_hint=rh,
        )
        try:
            raw = await self.server.llm_client.generate_or_raise(
                prompt,
                system_prompt=(
                    "You output only a single image-generation prompt for an environment or scene. "
                    "No quotes, markdown, labels, or preamble."
                ),
                max_tokens=500,
            )
        except LLMGenerationError as e:
            logger.warning("play suggest scene prompt LLM failed: %s", e)
            return {"ok": False, "error": "llm_failed", "detail": str(e)}
        text = (raw or "").strip().strip('"').strip("'")
        text = " ".join(text.split())
        if len(text) < 8:
            return {"ok": False, "error": "llm_prompt_too_short", "detail": text or "(empty)"}
        return {"ok": True, "prompt": text[:2000]}

    # ------------------------------------------------------------------
    # Image generation
    # ------------------------------------------------------------------

    async def generate_scene_image(
        self,
        username: str,
        password: str,
        scene_prompt: str,
        character_id: int | None = None,
        token: str = "",
    ) -> dict[str, Any]:
        """ComfyUI area workflow: save PNG under /media/rooms/ (or room-art); optional character_id persists URL for reload."""
        account, err = await resolve_play_account_or_error(
            self.server, token=token, username=username, password=password
        )
        if err or account is None:
            return err or {"ok": False, "error": "invalid_credentials"}
        account_id = account.id
        ip = (scene_prompt or "").strip()
        if len(ip) < 3:
            return {"ok": False, "error": "prompt_too_short"}
        if len(ip) > 4000:
            return {"ok": False, "error": "prompt_too_long"}
        cfg = self.server.config.comfyui
        area_wp = (cfg.area_workflow_path or "").strip() or cfg.workflow_path
        if not cfg.enabled or not resolve_config_asset_path(area_wp).is_file():
            return {
                "ok": False,
                "error": "comfyui_not_configured",
                **self.server.economy.public_fields(),
                "echo_credits": await self.server.economy.read_balance(account_id),
            }
        cost = int(cfg.area_generation_cost)
        ok_debit, err_debit, bal_after, charged = await self.server.economy.debit_for_generation(
            account_id, cost
        )
        if not ok_debit:
            return err_debit
        res = await self.generate_room_area_image(ip)
        if not res.get("ok"):
            if charged:
                await self.server.economy.refund(account_id, charged)
            return {
                **res,
                **self.server.economy.public_fields(),
                "echo_credits": await self.server.economy.read_balance(account_id),
            }
        scene_url = res.get("area_image_url")
        scene_url_str = str(scene_url).strip()[:2048] if scene_url else ""
        if scene_url and _is_safe_player_scene_storage_url(scene_url_str):
            async with self.server.db.session_factory() as db_session:
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
            **self.server.economy.public_fields(),
            "echo_credits": bal_after,
            "cost_charged": charged,
        }

    async def list_scene_gallery(
        self, username: str, password: str, *, token: str = ""
    ) -> dict[str, Any]:
        """List ComfyUI scene images recorded for this account (newest first)."""
        account, err = await resolve_play_account_or_error(
            self.server, token=token, username=username, password=password
        )
        if err or account is None:
            return err or {"ok": False, "error": "invalid_credentials"}
        q = (
            select(AccountSceneImage, Character.name)
            .outerjoin(Character, AccountSceneImage.character_id == Character.id)
            .where(AccountSceneImage.account_id == account.id)
            .order_by(AccountSceneImage.created_at.desc())
            .limit(200)
        )
        async with self.server.db.session_factory() as db_session:
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

    async def apply_scene_from_gallery(
        self,
        username: str,
        password: str,
        gallery_id: int,
        character_id: int,
        token: str = "",
    ) -> dict[str, Any]:
        """Set the active scene image for a character from a row in this account's gallery."""
        username = (username or "").strip()
        if not username and not token:
            return {"ok": False, "error": "username_required"}
        if gallery_id < 1 or character_id < 1:
            return {"ok": False, "error": "invalid_ids"}
        async with self.server.db.session_factory() as db_session:
            account = await resolve_play_account(
                db_session, self.server, token=token, username=username, password=password
            )
            if account is None:
                return {"ok": False, "error": "invalid_credentials"}
            aid = account.id
            row = await db_session.get(AccountSceneImage, gallery_id)
            if row is None or row.account_id != aid:
                return {"ok": False, "error": "gallery_item_not_found"}
            url = (row.image_url or "").strip()[:2048]
            if not _is_safe_player_scene_storage_url(url):
                return {"ok": False, "error": "invalid_stored_url"}
            char = await db_session.get(Character, character_id)
            if char is None or char.account_id != aid:
                return {"ok": False, "error": "character_not_owned"}
            char.last_scene_image_url = url
            await db_session.commit()
        return {"ok": True, "scene_image_url": url}

    async def generate_room_area_image(
        self,
        image_prompt: str,
        *,
        zone_id: str = "",
        room_slug: str = "",
    ) -> dict[str, Any]:
        """ComfyUI: save PNG; optional zone+slug writes next to room YAML for portable world content."""
        cfg = self.server.config.comfyui
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

    async def generate_portrait(
        self, username: str, password: str, appearance_prompt: str, *, token: str = ""
    ) -> dict[str, Any]:
        account, err = await resolve_play_account_or_error(
            self.server, token=token, username=username, password=password
        )
        if err or account is None:
            return err or {"ok": False, "error": "invalid_credentials"}
        account_id = account.id

        cfg = self.server.config.comfyui
        eco = self.server.economy.public_fields()
        if not cfg.enabled or not resolve_config_asset_path(cfg.workflow_path).is_file():
            return {
                "ok": True,
                "portrait_url": None,
                "note": "comfyui_not_configured",
                **eco,
                "echo_credits": await self.server.economy.read_balance(account_id),
            }

        cost = int(cfg.portrait_generation_cost)
        ok_debit, err_debit, bal_after, charged = await self.server.economy.debit_for_generation(
            account_id, cost
        )
        if not ok_debit:
            return err_debit

        try:
            png, _ = await generate_portrait_png(cfg, appearance_prompt)
        except Exception as e:
            logger.warning("ComfyUI portrait failed: %s", e, exc_info=True)
            if charged:
                await self.server.economy.refund(account_id, charged)
            return {
                "ok": False,
                "error": "comfyui_failed",
                "detail": str(e),
                **eco,
                "echo_credits": await self.server.economy.read_balance(account_id),
            }

        return {
            "ok": True,
            "portrait_url": save_portrait_png(png),
            **eco,
            "echo_credits": bal_after,
            "cost_charged": charged,
        }
