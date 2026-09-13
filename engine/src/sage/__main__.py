"""Entry point: `python -m sage` starts the Nexus server; subcommands manage the database."""

import sys

from sage.cli import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
