"""Conduit tests: the plugin package is importable directly; plugin_host loads it like a server."""

import sys
from pathlib import Path

from tests.plugins.conftest import plugin_host  # noqa: F401 - fixture for host-level tests

PLUGIN_DIR = Path(__file__).resolve().parents[1]
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))
