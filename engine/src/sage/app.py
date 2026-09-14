"""Global server singleton — all command handlers import app_instance from here."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sage.server import SageServer

# Global server instance, assigned by run_server() before any command handler runs.
# Typed non-optional: handlers import it lazily inside function bodies, after assignment.
app_instance: SageServer = None  # type: ignore[assignment]
