"""What is running: engine version, world package, loaded plugins, AI slots and who is online.

`GET /admin/world` is the admin console's single source for "which world is this and what is
loaded". Before it, no admin page said which world was running or which plugins it had.
"""

from __future__ import annotations

from importlib import metadata
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any

from fastapi import APIRouter, Depends

from sage.admin.admin_security import AdminContext
from sage.admin.route_helpers import require_any_tool

if TYPE_CHECKING:
    from sage.server import SageServer


def engine_version() -> str:
    try:
        return metadata.version("sage-engine")
    except metadata.PackageNotFoundError:
        return "unknown"


def _relative(path: Path | str | None) -> str | None:
    if path is None:
        return None
    from sage.core.config import resolve_project_root

    path = Path(path)
    try:
        return path.resolve().relative_to(resolve_project_root()).as_posix()
    except ValueError:
        return str(path)


def plugin_summary(host: Any) -> list[dict[str, Any]]:
    """Loaded plugins in load order, with what each registered (sealed against its manifest)."""
    tools = dict(getattr(host, "admin_tools", []) or [])
    out = []
    for record in getattr(host, "loaded", []) or []:
        info = record.manifest.plugin
        out.append(
            {
                "id": info.id,
                "name": info.name or info.id,
                "version": info.version,
                "engine": info.engine,
                "first_party": info.first_party,
                # Where it lives: "world" for worlds/<id>/plugins, "shared" for the plugins/ directory.
                "source": "world" if "worlds" in Path(record.path).resolve().parts else "shared",
                "trusted": record.trusted,
                "path": _relative(record.path),
                "depends": sorted(record.manifest.depends),
                "registered": {
                    kind: sorted(names) for kind, names in record.registered.items() if names
                },
                "admin_tool": tools.get(info.id),
            }
        )
    return out


def world_summary(server: Any) -> dict[str, Any]:
    world = server.world
    manifest = world.manifest.world
    sessions = list(server.session_manager.sessions.values())
    agents = sum(1 for s in sessions if getattr(s, "virtual", False))
    summary = {
        "engine": {"version": engine_version()},
        "world": {
            "id": manifest.id,
            "name": manifest.name,
            "version": manifest.version,
            "path": _relative(world.root),
            "room_types": list(world.manifest.content.room_types),
        },
        "plugins": plugin_summary(server.plugins),
        "ai_slots": server.prompt_manager.slots(),
        "online": {"players": len(sessions) - agents, "agents": agents},
        "dev_mode": bool(server.config.server.dev_mode),
    }
    # DEV-AUTH:BEGIN — the console warns while passwordless logins are on.
    summary["dev_login"] = bool(getattr(server.config.server, "dev_login", False))
    # DEV-AUTH:END
    return summary


def build_about_router(server: SageServer) -> APIRouter:
    router = APIRouter()

    @router.get("/admin/world")
    async def admin_world(
        _ctx: Annotated[AdminContext, Depends(require_any_tool("dashboard", "server", "forge"))],
    ):
        """The running world, engine version, loaded plugins, AI slots and online counts."""
        return world_summary(server)

    return router
