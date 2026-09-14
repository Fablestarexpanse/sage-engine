"""Serve the built player client (`engine/clients/player-ui/dist`) from Nexus at `/`.

With the client on the same origin as the API, a new install needs one terminal: the server. The
client is served from the router's 404 fallback rather than a `/` mount, so routes added later
(plugin routers mount while the server starts) are never shadowed. Only GET/HEAD requests for the
root, `/assets/...` and root-level files with an extension reach it, and only files inside the
build directory are served.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import FileResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


def is_client_path(path: str) -> bool:
    """Paths the client build may own: `/`, `/assets/*`, and root files such as `/favicon.svg`."""
    if path in ("/", "/index.html") or path.startswith("/assets/"):
        return True
    return path.count("/") == 1 and "." in path[1:]


def client_dir(server: Any) -> Path:
    from sage.core.config import resolve_project_root

    configured = Path(getattr(server.config.server, "player_client_dir", "") or "")
    return configured if configured.is_absolute() else resolve_project_root() / configured


def client_file(dist: Path, path: str) -> Path | None:
    """The file under `dist` for a request path, or None (missing, or outside `dist`)."""
    if not is_client_path(path):
        return None
    relative = "index.html" if path == "/" else path.lstrip("/")
    root = dist.resolve()
    candidate = (root / relative).resolve()
    if not candidate.is_relative_to(root) or not candidate.is_file():
        return None
    return candidate


def install(app: FastAPI, server: Any) -> None:
    async def not_found_serves_client(request: Request, exc: StarletteHTTPException):
        if exc.status_code == 404 and request.method in ("GET", "HEAD"):
            found = client_file(client_dir(server), request.url.path)
            if found is not None:
                # index.html names hashed asset files, so it must never be cached; assets can be.
                cache = "no-cache" if found.name == "index.html" else "public, max-age=3600"
                return FileResponse(found, headers={"Cache-Control": cache})
        return await http_exception_handler(request, exc)

    app.add_exception_handler(StarletteHTTPException, not_found_serves_client)
