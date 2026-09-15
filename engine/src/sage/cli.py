"""Command line: run the server, migrate the database, uninstall plugins.

python -m sage                                  run the server
python -m sage quickstart [--world ID] [--no-docker] [--no-client] [--no-server]   config, services, database, server
python -m sage world new ID [--name NAME] [--dir DIR] [--force]   a new world package (one room, no map)
python -m sage db create [--world ID]           create the world's database if it is missing
python -m sage db status [--world ID]           list unapplied core/plugin migrations
python -m sage db upgrade [--world ID]          apply every core and plugin migration
python -m sage plugin uninstall ID [--purge-state]
python -m sage validate [--world ID] [--zone ZONE] [--info]
python -m sage schema export [--world ID] [--out PATH]   content JSON Schema for editors
"""

from __future__ import annotations

import argparse
import asyncio
import sys


def _world_context():
    from sage.commands.registry import CommandRegistry
    from sage.core.config import load_config, resolve_project_root
    from sage.plugins.loader import discover
    from sage.state.postgres import PostgresState
    from sage.world.package import select_world

    config = load_config()
    root = resolve_project_root()
    world = select_world(root / config.server.worlds_dir, config.server.world)
    records = discover(world, root / "plugins", [root / "plugins", root / "worlds"])
    del CommandRegistry  # discovery only: nothing is imported or registered
    return config, world, records, PostgresState(config.database).url


def _use_world(world: str | None) -> None:
    """Point config at another world and its own database (`sage_<id>`), as quickstart does."""
    import os

    from sage.core.config import load_config
    from sage.quickstart import database_for

    if not world:
        return
    config = load_config()
    os.environ["SAGE_SERVER__WORLD"] = world
    os.environ["SAGE_DATABASE__DATABASE"] = database_for(
        world, config.server.world, config.database.database
    )


def _world(args: argparse.Namespace) -> int:
    from pathlib import Path

    from sage.core.config import load_config, resolve_project_root
    from sage.world.new import WorldNewError, create_world

    root = resolve_project_root()
    worlds_dir = Path(args.dir) if args.dir else root / load_config().server.worlds_dir
    try:
        result = create_world(args.world_id, worlds_dir, root, name=args.name, force=args.force)
    except WorldNewError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    for rel in result.written:
        print(f"  wrote {result.path.name}/{rel}")
    for level, lines in (("error", result.errors), ("warning", result.warnings)):
        for line in lines:
            print(f"{level}: {line}", file=sys.stderr)
    if result.errors or result.warnings:
        print(f"{result.path}: does not validate; the files are kept", file=sys.stderr)
        return 1
    wid = args.world_id
    print(f"\n{result.path} is ready: one room, start:arrival.")
    print("Next:")
    print(f"  1. draw the map in WorldForge (open the repository root, pick {wid})")
    print(f"  2. python -m sage validate --world {wid}")
    print(f"  3. sage quickstart --world {wid}")
    print(
        f"     (or on a running setup: sage db create --world {wid} && sage db upgrade --world {wid})"
    )
    return 0


def _db(args: argparse.Namespace) -> int:
    from alembic import command
    from sage.plugins.migrations import alembic_config, pending_heads

    _use_world(args.world)

    if args.action == "create":
        from sage.core.config import load_config
        from sage.quickstart import QuickstartError, ensure_database

        config = load_config()
        try:
            created = asyncio.run(ensure_database(config.database, config.database.database))
        except (QuickstartError, OSError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(f"{config.database.database}: " + ("created" if created else "already exists"))
        return 0

    config, world, records, url = _world_context()
    cfg = alembic_config([r.path for r in records])
    try:
        if args.action == "status":
            pending = pending_heads(cfg, url)
            target = f"{config.database.database} (world {world.id})"
            print(f"{target}: " + ("up to date" if not pending else f"unapplied heads {pending}"))
            return 1 if pending else 0
        command.upgrade(cfg, "heads")
    except Exception as exc:
        if not _missing_database(exc):
            raise
        flag = f" --world {args.world}" if args.world else ""
        print(
            f"error: database {config.database.database} does not exist; "
            f"run: python -m sage db create{flag}",
            file=sys.stderr,
        )
        return 1
    print(f"{config.database.database}: upgraded core and {len(records)} plugin branch(es)")
    return 0


def _missing_database(exc: BaseException | None) -> bool:
    """True when Postgres refused the connection because the database does not exist."""
    while exc is not None:
        if type(exc).__name__ == "InvalidCatalogNameError":
            return True
        exc = exc.__cause__ or exc.__context__
    return False


def _plugin(args: argparse.Namespace) -> int:
    from sage.plugins.manifest import PluginError
    from sage.plugins.uninstall import uninstall_plugin

    _, world, records, url = _world_context()
    try:
        report = asyncio.run(
            uninstall_plugin(world, records, args.plugin_id, url, purge_state=args.purge_state)
        )
    except PluginError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    for line in report or [f"{args.plugin_id}: nothing to remove"]:
        print(line)
    return 0


def _validate(args: argparse.Namespace) -> int:
    """Lint a world's content (sage.world.lint); exit 1 when there are errors."""
    from sage.core.config import load_config, resolve_project_root
    from sage.world.lint import lint_world
    from sage.world.package import WorldPackageError, select_world

    config = load_config()
    root = resolve_project_root()
    try:
        world = select_world(root / config.server.worlds_dir, args.world or config.server.world)
    except WorldPackageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    report = lint_world(world, zone=args.zone)
    levels = [("error", report.errors), ("warning", report.warnings)]
    if args.info:
        levels.append(("info", report.info))
    for level, lines in levels:
        for line in lines:
            print(f"{level}: {line}")
    scope = f"zone {args.zone}" if args.zone else f"{len(report.rooms)} rooms"
    print(f"{world.id} ({scope}): {len(report.errors)} error(s), {len(report.warnings)} warning(s)")
    return 1 if report.errors else 0


def _schema(args: argparse.Namespace) -> int:
    """Write the world's content schema (engine models + enabled plugins' extension fields)."""
    from pathlib import Path

    from sage.core.config import load_config, resolve_project_root
    from sage.plugins.offline import registration_host
    from sage.world.package import WorldPackageError, select_world
    from sage.world.schema import content_schema, dumps

    config = load_config()
    root = resolve_project_root()
    try:
        world = select_world(root / config.server.worlds_dir, args.world or config.server.world)
    except WorldPackageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    with registration_host(world, root) as host:
        text = dumps(content_schema(world, host.extensions))
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8", newline="\n")
        print(f"{world.id}: wrote {args.out}")
    else:
        sys.stdout.write(text)
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="sage", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="group")
    db = sub.add_parser("db", help="database migrations")
    db.add_argument("action", choices=["create", "status", "upgrade"])
    db.add_argument("--world", help="another world, in its own database sage_<id>")
    world = sub.add_parser("world", help="world packages")
    world_sub = world.add_subparsers(dest="action", required=True)
    new = world_sub.add_parser("new", help="make a world package with one start room and no map")
    new.add_argument("world_id", help="lowercase letters, digits and underscores")
    new.add_argument("--name", help="display name (default: the id in title case)")
    new.add_argument("--dir", help="worlds directory (default: the configured worlds_dir)")
    new.add_argument("--force", action="store_true", help="rewrite the template's files if present")
    quick = sub.add_parser(
        "quickstart", help="config, Postgres and Redis, database and migrations, then the server"
    )
    quick.add_argument("--world", help="world id (default: the configured world, else demo)")
    quick.add_argument(
        "--no-docker", action="store_true", help="use Postgres and Redis already running"
    )
    quick.add_argument("--no-server", action="store_true", help="stop after migrations")
    quick.add_argument("--no-client", action="store_true", help="do not build the player client")
    plugin = sub.add_parser("plugin", help="plugin management")
    plugin_sub = plugin.add_subparsers(dest="action", required=True)
    uninstall = plugin_sub.add_parser("uninstall", help="remove a plugin and its tables")
    uninstall.add_argument("plugin_id")
    uninstall.add_argument("--purge-state", action="store_true")
    validate = sub.add_parser("validate", help="check a world's content without a server")
    validate.add_argument("--world", help="world id (default: the configured world)")
    validate.add_argument("--zone", help="check one zone")
    validate.add_argument("--info", action="store_true", help="also print informational notes")
    schema = sub.add_parser("schema", help="content schema for editors")
    schema.add_argument("action", choices=["export"])
    schema.add_argument("--world", help="world id (default: the configured world)")
    schema.add_argument("--out", help="file to write (default: stdout)")
    args = parser.parse_args(argv)

    if args.group == "db":
        return _db(args)
    if args.group == "world":
        return _world(args)
    if args.group == "quickstart":
        from sage.quickstart import QuickstartError
        from sage.quickstart import run as quickstart

        try:
            return quickstart(
                args.world,
                docker=not args.no_docker,
                server=not args.no_server,
                client=not args.no_client,
            )
        except QuickstartError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
    if args.group == "plugin":
        return _plugin(args)
    if args.group == "validate":
        return _validate(args)
    if args.group == "schema":
        return _schema(args)

    from sage.server import run_server

    try:
        asyncio.run(run_server())
    except KeyboardInterrupt:
        return 0
    return 0


def run() -> None:
    """Console-script entry point."""
    sys.exit(main(sys.argv[1:]))
