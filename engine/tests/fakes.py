"""Shared in-memory fakes for hermetic tests — no Redis/Postgres/LLM required."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

from sage.world.models import EntityTemplate, ItemTemplate, RoomModel
from sage.world.package import Currency
from sage.world.wallet import Wallet

# Repository root.
ROOT = Path(__file__).resolve().parents[2]


def fake_wallet(key: str = "coin", starting: int = 100) -> Wallet:
    """A wallet over a one-currency test world (label resolves through the active lexicon)."""
    world = SimpleNamespace(
        id="test", currencies=[Currency(key=key, label=f"currency.{key}.name", starting=starting)]
    )
    return Wallet(world)


class FakeRedisClient:
    """The raw-client commands plugins and engine services use (strings, hashes, lists)."""

    def __init__(self) -> None:
        self.strings: dict[str, str] = {}
        self.hashes: dict[str, dict[str, str]] = {}
        self.lists: dict[str, list[str]] = {}

    async def get(self, key):
        return self.strings.get(key)

    async def set(self, key, value, **_):
        self.strings[key] = str(value)

    async def delete(self, *keys):
        for key in keys:
            self.strings.pop(key, None)
            self.hashes.pop(key, None)
            self.lists.pop(key, None)

    async def getdel(self, key):
        return self.strings.pop(key, None)

    async def incrby(self, key, amount=1):
        value = int(self.strings.get(key, 0)) + int(amount)
        self.strings[key] = str(value)
        return value

    async def expire(self, key, seconds):
        return True

    async def hget(self, key, field):
        return self.hashes.get(key, {}).get(field)

    async def hset(self, key, field, value):
        self.hashes.setdefault(key, {})[field] = value

    async def hdel(self, key, *fields):
        for field in fields:
            self.hashes.get(key, {}).pop(field, None)

    async def hgetall(self, key):
        return dict(self.hashes.get(key, {}))

    async def hincrby(self, key, field, amount=1):
        bucket = self.hashes.setdefault(key, {})
        bucket[field] = str(int(bucket.get(field, 0)) + int(amount))
        return int(bucket[field])

    async def lpush(self, key, *values):
        self.lists.setdefault(key, [])[:0] = list(reversed(values))
        return len(self.lists[key])

    async def ltrim(self, key, start, end):
        self.lists[key] = self.lists.get(key, [])[start : end + 1]

    async def lrange(self, key, start, end):
        items = self.lists.get(key, [])
        return items[start:] if end == -1 else items[start : end + 1]


class FakeRedis:
    """Dict-backed drop-in for the RedisState methods game code uses."""

    namespace = ""
    is_connected = True

    def __init__(self) -> None:
        self.client = FakeRedisClient()
        self.locations: dict[str, str] = {}
        self.stats: dict[str, dict[str, Any]] = {}
        self.inventories: dict[str, list[Any]] = {}
        self.room_players: dict[str, set[str]] = {}
        self.entity_states: dict[str, dict[str, Any]] = {}
        self.room_entities: dict[str, set[str]] = {}
        self.item_states: dict[str, dict[str, Any]] = {}
        self.room_items: dict[str, set[str]] = {}

    def key(self, raw: str) -> str:
        return raw

    def unkey(self, stored: str) -> str:
        return stored

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
    """Serves canned Pydantic models."""

    def __init__(self) -> None:
        self.rooms: dict[str, RoomModel] = {}
        self.entity_templates: dict[str, EntityTemplate] = {}
        self.item_templates: dict[str, ItemTemplate] = {}

    def get_room(self, room_id: str) -> RoomModel | None:
        return self.rooms.get(room_id)

    def get_entity_template(self, entity_id: str) -> EntityTemplate | None:
        return self.entity_templates.get(entity_id)

    def get_item_template(self, item_id: str) -> ItemTemplate | None:
        return self.item_templates.get(item_id)


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
    """The repository's full reference world: the package with the most rooms.

    Engine tests that need real content (zones, factions, agents) read it from here.
    """
    from sage.world.package import available_worlds, load_world_package

    worlds = [load_world_package(ROOT / "worlds" / w) for w in available_worlds(ROOT / "worlds")]
    if not worlds:
        raise RuntimeError("no world packages in the repository")
    return max(worlds, key=lambda w: len(list(w.zones_dir.glob("*/rooms/*.yaml"))))


def make_fake_server() -> SimpleNamespace:
    """A SageServer stand-in with the attributes command handlers touch."""
    from sage.parser.dispatcher import CommandDispatcher
    from sage.world.spawner import EntitySpawnManager

    server = SimpleNamespace()
    server.redis = FakeRedis()
    server.content_loader = FakeContentLoader()
    server.world = repo_world()
    server.config = SimpleNamespace(server=SimpleNamespace())
    server.dispatcher = CommandDispatcher()
    from sage.llm.prompts import PromptManager

    # A world with no AI templates: every slot disabled, so commands take their plain paths.
    server.prompt_manager = PromptManager(ROOT / "worlds" / "_no_ai")
    server.session_manager = SimpleNamespace(
        player_to_session={}, get_session_by_player=lambda pid: None
    )
    server.spawner = EntitySpawnManager(server)  # type: ignore[arg-type]
    from sage.core.resolvers import Resolvers
    from sage.world.slots import define_engine_slots

    server.resolvers = Resolvers()
    define_engine_slots(server.resolvers)
    return server
