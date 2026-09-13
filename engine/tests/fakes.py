"""Shared in-memory fakes for hermetic tests — no Redis/Postgres/LLM required."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

from sage.world.models import EntityTemplate, ItemTemplate, RoomModel
from sage.world.package import Currency
from sage.world.wallet import Wallet

# Repository root (world content lives at <root>/content during the SAGE transition).
ROOT = Path(__file__).resolve().parents[2]


def fake_wallet(key: str = "coin", starting: int = 100) -> Wallet:
    """A wallet over a one-currency test world (label resolves through the active lexicon)."""
    world = SimpleNamespace(
        id="test", currencies=[Currency(key=key, label=f"currency.{key}.name", starting=starting)]
    )
    return Wallet(world)


class FakeRedis:
    """Dict-backed drop-in for the RedisState methods game code uses."""

    def __init__(self) -> None:
        self.locations: dict[str, str] = {}
        self.stats: dict[str, dict[str, Any]] = {}
        self.inventories: dict[str, list[Any]] = {}
        self.room_players: dict[str, set[str]] = {}
        self.entity_states: dict[str, dict[str, Any]] = {}
        self.room_entities: dict[str, set[str]] = {}
        self.item_states: dict[str, dict[str, Any]] = {}
        self.room_items: dict[str, set[str]] = {}

    # Player location
    async def get_player_location(self, player_id: str) -> str | None:
        return self.locations.get(player_id)

    async def set_player_location(self, player_id: str, room_id: str) -> None:
        old = self.locations.get(player_id)
        if old:
            self.room_players.get(old, set()).discard(player_id)
        self.locations[player_id] = room_id
        self.room_players.setdefault(room_id, set()).add(player_id)

    async def get_room_players(self, room_id: str) -> set[str]:
        return set(self.room_players.get(room_id, set()))

    async def add_player_to_room(self, player_id: str, room_id: str) -> None:
        self.room_players.setdefault(room_id, set()).add(player_id)

    async def remove_player_from_room(self, player_id: str, room_id: str) -> None:
        self.room_players.get(room_id, set()).discard(player_id)

    async def get_all_active_player_ids(self) -> list[str]:
        return list(self.locations.keys())

    # Player stats / inventory
    async def get_player_stats(self, player_id: str) -> dict[str, Any]:
        return self.stats.get(player_id, {})

    async def set_player_stats(self, player_id: str, stats: dict[str, Any]) -> None:
        self.stats[player_id] = dict(stats)

    async def get_player_inventory(self, player_id: str) -> list[Any]:
        return list(self.inventories.get(player_id, []))

    async def set_player_inventory(self, player_id: str, inventory: list[Any]) -> None:
        self.inventories[player_id] = list(inventory)

    # Entities
    async def get_entity_state(self, entity_id: str) -> dict[str, Any] | None:
        return self.entity_states.get(entity_id)

    async def set_entity_state(self, entity_id: str, state: dict[str, Any]) -> None:
        self.entity_states[entity_id] = dict(state)

    async def delete_entity_state(self, entity_id: str) -> None:
        self.entity_states.pop(entity_id, None)

    async def get_room_entities(self, room_id: str) -> set[str]:
        return set(self.room_entities.get(room_id, set()))

    async def add_entity_to_room(self, entity_id: str, room_id: str) -> None:
        self.room_entities.setdefault(room_id, set()).add(entity_id)

    async def remove_entity_from_room(self, entity_id: str, room_id: str) -> None:
        self.room_entities.get(room_id, set()).discard(entity_id)

    # Floor items
    async def get_item_state(self, item_id: str) -> dict[str, Any] | None:
        return self.item_states.get(item_id)

    async def set_item_state(self, item_id: str, state: dict[str, Any]) -> None:
        self.item_states[item_id] = dict(state)

    async def delete_item_state(self, item_id: str) -> None:
        self.item_states.pop(item_id, None)

    async def get_room_items(self, room_id: str) -> set[str]:
        return set(self.room_items.get(room_id, set()))

    async def add_item_to_room(self, item_id: str, room_id: str) -> None:
        self.room_items.setdefault(room_id, set()).add(item_id)

    async def remove_item_from_room(self, item_id: str, room_id: str) -> None:
        self.room_items.get(room_id, set()).discard(item_id)


class FakeContentLoader:
    """Serves canned Pydantic models; proficiency registry loads from real content/."""

    def __init__(self) -> None:
        self.rooms: dict[str, RoomModel] = {}
        self.entity_templates: dict[str, EntityTemplate] = {}
        self.item_templates: dict[str, ItemTemplate] = {}
        self._registry = None

    def get_room(self, room_id: str) -> RoomModel | None:
        return self.rooms.get(room_id)

    def get_entity_template(self, entity_id: str) -> EntityTemplate | None:
        return self.entity_templates.get(entity_id)

    def get_item_template(self, item_id: str) -> ItemTemplate | None:
        return self.item_templates.get(item_id)

    def get_proficiency_registry(self):
        if self._registry is None:
            from sage.proficiencies.catalog_loader import load_proficiency_catalog_from_disk
            from sage.proficiencies.registry import ProficiencyRegistry

            doc = load_proficiency_catalog_from_disk(ROOT / "content")
            self._registry = ProficiencyRegistry(doc.leaves)
        return self._registry


class StubProtocol:
    """Records sent text; scripted receive() lines."""

    def __init__(self, incoming: list[str] | None = None) -> None:
        self.sent: list[str] = []
        self.incoming = list(incoming or [])
        self._connected = True
        self.closed = False

    async def send(self, message: str) -> None:
        self.sent.append(message)

    async def receive(self) -> str | None:
        if not self.incoming:
            self._connected = False
            return None
        return self.incoming.pop(0)

    async def close(self) -> None:
        self._connected = False
        self.closed = True

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def peer_info(self) -> str:
        return "test-peer"


class StubSession:
    """Duck-typed Session for command handler tests."""

    def __init__(self, player_id: str | None = "tester") -> None:
        self.id = "session-test"
        self.player_id = player_id
        self.sent: list[str] = []
        self.closed = False
        self.protocol = StubProtocol()

    async def send(self, message: str) -> None:
        self.sent.append(message)

    async def say(self, key: str, **variables) -> None:
        from sage import lexicon

        self.sent.append(lexicon.t(key, **variables))

    async def send_prompt(self) -> None:
        pass

    async def close(self) -> None:
        self.closed = True

    async def end(self, reason: str, text: str | None = None) -> None:
        if text:
            self.sent.append(text)
        self.end_reason = reason
        self.closed = True


def repo_world():
    """The world package whose content is the repository's content/ tree.

    During the SAGE transition engine tests read that content directly.
    """
    from sage.world.package import available_worlds, load_world_package

    for world_id in available_worlds(ROOT / "worlds"):
        world = load_world_package(ROOT / "worlds" / world_id)
        if world.content_dir == (ROOT / "content").resolve():
            return world
    raise RuntimeError("no world package points at the repository content/ tree")


def make_fake_server() -> SimpleNamespace:
    """A SageServer stand-in with the attributes command handlers touch."""
    from sage.parser.dispatcher import CommandDispatcher
    from sage.world.spawner import EntitySpawnManager

    server = SimpleNamespace()
    server.redis = FakeRedis()
    server.content_loader = FakeContentLoader()
    server.world = repo_world()
    server.config = SimpleNamespace(server=SimpleNamespace(proficiency_combat_hybrid=True))
    server.dispatcher = CommandDispatcher()
    server.session_manager = SimpleNamespace(
        player_to_session={}, get_session_by_player=lambda pid: None
    )
    server.spawner = EntitySpawnManager(server)  # type: ignore[arg-type]
    return server
