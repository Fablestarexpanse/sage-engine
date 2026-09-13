"""Suite-wide fixtures."""

import os

import pytest

from fablestar import telemetry

# Command tests exercise real handlers that emit telemetry; without this they
# append fake kills and missions to the live soak log in logs/.
telemetry.disable()

_LIVE_SKIP = pytest.mark.skip(
    reason="live tier: set SAGE_LIVE_TESTS=1 with Postgres and Redis running"
)


def pytest_collection_modifyitems(config, items):
    """Live-tier tests (STANDARDS 3.5) only run when explicitly enabled."""
    if os.environ.get("SAGE_LIVE_TESTS") == "1":
        return
    for item in items:
        if item.get_closest_marker("live"):
            item.add_marker(_LIVE_SKIP)
