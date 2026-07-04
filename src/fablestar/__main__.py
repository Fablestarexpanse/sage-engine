"""Entry point: python -m fablestar starts the Nexus server."""

import asyncio
import sys

from fablestar.server import run_server


def main():
    """Main entry point for the fablestar package."""
    try:
        asyncio.run(run_server())
    except KeyboardInterrupt:
        # Graceful exit for CTRL+C outside of the loop
        sys.exit(0)


if __name__ == "__main__":
    main()
